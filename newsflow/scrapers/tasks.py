import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from newsflow.news.models import Article
from newsflow.news.models import NewsSource
from newsflow.scrapers.services import NewsScraperService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def scrape_single_source(self, source_id: int) -> dict[str, int]:
    """
    Scrape articles from a single news source.

    Args:
        source_id: ID of the NewsSource to scrape

    Returns:
        Dictionary with scraping statistics
    """
    logger.info(f"Starting scraping task for source ID: {source_id}")

    try:
        source = NewsSource.objects.get(id=source_id, is_active=True)
    except NewsSource.DoesNotExist:
        logger.error(f"Active NewsSource with ID {source_id} not found")
        return {"success": 0, "failed": 0, "duplicates": 0, "error": "Source not found"}

    # Check if source is due for scraping
    if not source.is_due_for_scraping:
        logger.info(f"Source {source.name} is not due for scraping yet")
        return {"success": 0, "failed": 0, "duplicates": 0, "skipped": True}

    scraper = NewsScraperService()

    try:
        # Record start time for performance tracking
        start_time = timezone.now()

        # Perform scraping based on source type
        if source.source_type == "rss" and source.rss_feed:
            stats = scraper.scrape_rss_feed(source_id)
        else:
            stats = scraper.scrape_source(source_id)

        # Update performance metrics
        end_time = timezone.now()
        response_time = (end_time - start_time).total_seconds()

        # Update source response time (rolling average)
        if source.average_response_time:
            source.average_response_time = (
                source.average_response_time + response_time
            ) / 2
        else:
            source.average_response_time = response_time

        # Update success rate
        total_attempts = stats["success"] + stats["failed"]
        if total_attempts > 0:
            source.update_success_rate(stats["success"], total_attempts)

        source.save(update_fields=["average_response_time"])

        logger.info(
            f"Completed scraping for {source.name}: "
            f"{stats['success']} articles saved, {stats['failed']} failed, "
            f"{stats['duplicates']} duplicates in {response_time:.2f}s",
        )

        return stats

    except Exception as e:
        logger.error(f"Failed to scrape source {source.name}: {e}")

        # Update failure statistics
        source.update_success_rate(0, 1)

        # Re-raise for Celery retry mechanism
        raise


@shared_task
def scrape_all_active_sources() -> dict[str, int]:
    """
    Scrape all active news sources that are due for scraping.

    Returns:
        Aggregated statistics for all sources
    """
    logger.info("Starting bulk scraping of all active sources")

    sources_to_scrape = NewsSource.objects.needs_scraping()
    total_stats = {"success": 0, "failed": 0, "duplicates": 0, "sources_processed": 0}

    if not sources_to_scrape:
        logger.info("No sources are due for scraping")
        return total_stats

    logger.info(f"Found {len(sources_to_scrape)} sources due for scraping")

    # Process sources in parallel using Celery's group/chord
    from celery import group

    # Create a group of scraping tasks
    scraping_jobs = group(
        scrape_single_source.s(source.id) for source in sources_to_scrape
    )

    # Execute the group and wait for results
    try:
        result = scraping_jobs.apply_async()
        results = result.get(timeout=3600)  # 1 hour timeout

        # Aggregate results
        for source_stats in results:
            if isinstance(source_stats, dict) and "error" not in source_stats:
                total_stats["success"] += source_stats.get("success", 0)
                total_stats["failed"] += source_stats.get("failed", 0)
                total_stats["duplicates"] += source_stats.get("duplicates", 0)
                total_stats["sources_processed"] += 1

    except Exception as e:
        logger.error(f"Failed to execute bulk scraping: {e}")
        # Fall back to sequential processing
        for source in sources_to_scrape:
            try:
                source_stats = scrape_single_source.apply(args=[source.id])
                if (
                    isinstance(source_stats.result, dict)
                    and "error" not in source_stats.result
                ):
                    total_stats["success"] += source_stats.result.get("success", 0)
                    total_stats["failed"] += source_stats.result.get("failed", 0)
                    total_stats["duplicates"] += source_stats.result.get(
                        "duplicates",
                        0,
                    )
                    total_stats["sources_processed"] += 1
            except Exception as source_error:
                logger.error(f"Failed to scrape source {source.name}: {source_error}")
                continue

    logger.info(
        f"Bulk scraping completed: {total_stats['sources_processed']} sources processed, "
        f"{total_stats['success']} total articles saved",
    )

    return total_stats


@shared_task
def scheduled_scraper() -> dict[str, int]:
    """
    Periodic task to check and scrape sources that are due for scraping.
    This task is called by Celery Beat every 15 minutes.

    Returns:
        Scraping statistics
    """
    logger.info("Running scheduled scraper check")

    # Get sources that need scraping
    sources_due = NewsSource.objects.needs_scraping()

    if not sources_due:
        logger.info("No sources are due for scraping")
        return {
            "sources_checked": NewsSource.objects.active().count(),
            "sources_scraped": 0,
        }

    logger.info(f"Found {len(sources_due)} sources due for scraping")

    # Trigger scraping for each source
    stats = {
        "sources_checked": NewsSource.objects.active().count(),
        "sources_scraped": 0,
    }

    for source in sources_due:
        try:
            # Launch async scraping task
            scrape_single_source.delay(source.id)
            stats["sources_scraped"] += 1
            logger.info(f"Queued scraping task for {source.name}")
        except Exception as e:
            logger.error(f"Failed to queue scraping task for {source.name}: {e}")

    return stats


@shared_task
def cleanup_old_articles(days_old: int = 30) -> dict[str, int]:
    """
    Clean up old articles based on configured retention policy.

    Args:
        days_old: Number of days after which articles should be archived/deleted

    Returns:
        Cleanup statistics
    """
    logger.info(f"Starting cleanup of articles older than {days_old} days")

    cutoff_date = timezone.now() - timedelta(days=days_old)

    # Find old articles
    old_articles = Article.objects.filter(
        scraped_at__lt=cutoff_date,
        is_published=True,  # Only clean up published articles
    )

    total_count = old_articles.count()

    if total_count == 0:
        logger.info("No old articles found for cleanup")
        return {"archived": 0, "deleted": 0}

    logger.info(f"Found {total_count} articles older than {days_old} days")

    stats = {"archived": 0, "deleted": 0}

    try:
        # For now, we'll just mark them as unpublished (archived)
        # In the future, you might want to move them to a separate table or delete entirely
        updated_count = old_articles.update(is_published=False)
        stats["archived"] = updated_count

        logger.info(f"Archived {updated_count} old articles")

        # Optionally, delete articles older than 1 year
        very_old_cutoff = timezone.now() - timedelta(days=365)
        very_old_articles = Article.objects.filter(
            scraped_at__lt=very_old_cutoff,
            is_published=False,
        )

        deleted_count, _ = very_old_articles.delete()
        stats["deleted"] = deleted_count

        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} very old articles (>1 year)")

    except Exception as e:
        logger.error(f"Failed to cleanup old articles: {e}")
        raise

    return stats


@shared_task
def update_source_statistics(source_id: int) -> dict[str, any]:
    """
    Update performance statistics for a news source.

    Args:
        source_id: ID of the NewsSource to update

    Returns:
        Updated statistics
    """
    try:
        source = NewsSource.objects.get(id=source_id)
    except NewsSource.DoesNotExist:
        logger.error(f"NewsSource {source_id} not found")
        return {"error": "Source not found"}

    try:
        # Calculate articles scraped in last 24 hours
        yesterday = timezone.now() - timedelta(hours=24)
        recent_articles = source.articles.filter(scraped_at__gte=yesterday).count()

        # Calculate average articles per day over last 7 days
        week_ago = timezone.now() - timedelta(days=7)
        weekly_articles = source.articles.filter(scraped_at__gte=week_ago).count()
        avg_articles_per_day = weekly_articles / 7

        # Update source metadata (you might want to add these fields to NewsSource model)
        stats = {
            "source_name": source.name,
            "articles_last_24h": recent_articles,
            "avg_articles_per_day": round(avg_articles_per_day, 2),
            "total_articles": source.total_articles_scraped,
            "success_rate": source.success_rate,
            "last_scraped": source.last_scraped,
            "is_active": source.is_active,
        }

        logger.info(f"Updated statistics for {source.name}: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Failed to update statistics for source {source_id}: {e}")
        return {"error": str(e)}


@shared_task
def scrape_single_article(url: str, source_id: int | None = None) -> dict[str, any]:
    """
    Scrape a single article from URL.

    Args:
        url: Article URL to scrape
        source_id: Optional source ID for configuration

    Returns:
        Scraping result
    """
    logger.info(f"Scraping single article: {url}")

    scraper = NewsScraperService()

    try:
        source = None
        if source_id:
            source = NewsSource.objects.get(id=source_id)

        article_data = scraper.scrape_article(url, source)

        if not article_data:
            return {"success": False, "error": "Failed to scrape article"}

        # Validate quality
        is_valid, reason = scraper.validate_article_quality(article_data)
        if not is_valid:
            return {
                "success": False,
                "error": f"Article quality validation failed: {reason}",
            }

        # Check for duplicates
        if source and scraper._is_duplicate_article(url, article_data["title"], source):
            return {"success": False, "error": "Duplicate article"}

        # Save article
        if source:
            article = scraper._save_article(article_data, source)
            if article:
                return {
                    "success": True,
                    "article_id": article.id,
                    "title": article.title,
                    "url": article.url,
                }
        else:
            # Return article data without saving if no source specified
            return {
                "success": True,
                "article_data": article_data,
            }

        return {"success": False, "error": "Failed to save article"}

    except Exception as e:
        logger.error(f"Failed to scrape single article {url}: {e}")
        return {"success": False, "error": str(e)}


@shared_task
def health_check_sources() -> dict[str, any]:
    """
    Perform health checks on all active news sources.

    Returns:
        Health check results
    """
    logger.info("Starting health check for all sources")

    active_sources = NewsSource.objects.active()
    results = {
        "total_sources": active_sources.count(),
        "healthy_sources": 0,
        "unhealthy_sources": 0,
        "source_details": [],
    }

    for source in active_sources:
        try:
            # Simple health check - try to access the base URL
            import requests

            response = requests.head(source.base_url, timeout=10)
            is_healthy = response.status_code < 400

            if is_healthy:
                results["healthy_sources"] += 1
            else:
                results["unhealthy_sources"] += 1

            results["source_details"].append(
                {
                    "name": source.name,
                    "url": source.base_url,
                    "healthy": is_healthy,
                    "status_code": response.status_code,
                    "last_scraped": source.last_scraped,
                    "success_rate": source.success_rate,
                },
            )

        except Exception as e:
            results["unhealthy_sources"] += 1
            results["source_details"].append(
                {
                    "name": source.name,
                    "url": source.base_url,
                    "healthy": False,
                    "error": str(e),
                    "last_scraped": source.last_scraped,
                    "success_rate": source.success_rate,
                },
            )

    logger.info(
        f"Health check completed: {results['healthy_sources']} healthy, "
        f"{results['unhealthy_sources']} unhealthy sources",
    )

    return results
