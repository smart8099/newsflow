"""
Celery tasks for NewsFlow news processing.

Handles sentiment analysis, search vector updates, content summarization,
and other background processing tasks.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def analyze_article_sentiment(self, article_id: int, force_update: bool = False):
    """
    Analyze sentiment for a single article.

    Args:
        article_id: ID of the article to analyze
        force_update: Whether to force update existing sentiment data

    Returns:
        Dictionary with sentiment analysis results
    """
    try:
        from .models import Article
        from .sentiment import SentimentAnalyzer

        article = Article.objects.get(id=article_id)

        # Skip if already analyzed (unless forced)
        if not force_update and not article.needs_sentiment_analysis():
            logger.info(f"Article {article_id} already has sentiment data")
            return {
                "article_id": article_id,
                "status": "skipped",
                "sentiment_label": article.sentiment_label,
                "sentiment_score": article.sentiment_score,
            }

        # Initialize sentiment analyzer
        analyzer = SentimentAnalyzer(use_transformers=True)

        # Analyze sentiment
        text_to_analyze = f"{article.title} {article.content}"
        sentiment_result = analyzer.analyze_sentiment(text_to_analyze)

        # Update article with sentiment data
        with transaction.atomic():
            article.sentiment_score = sentiment_result["score"]
            article.sentiment_label = sentiment_result["label"]
            article.save(update_fields=["sentiment_score", "sentiment_label"])

        logger.info(
            f"Analyzed sentiment for article {article_id}: "
            f"{sentiment_result['label']} (score: {sentiment_result['score']:.3f})",
        )

        return {
            "article_id": article_id,
            "status": "completed",
            "sentiment_label": sentiment_result["label"],
            "sentiment_score": sentiment_result["score"],
            "confidence": sentiment_result.get("confidence", 0.0),
            "method": sentiment_result.get("method", "unknown"),
        }

    except Article.DoesNotExist:
        logger.error(f"Article {article_id} not found")
        return {
            "article_id": article_id,
            "status": "error",
            "error": "Article not found",
        }
    except Exception as e:
        logger.error(f"Error analyzing sentiment for article {article_id}: {e}")
        # Retry on failure
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2**self.request.retries))
        return {
            "article_id": article_id,
            "status": "error",
            "error": str(e),
        }


@shared_task
def batch_analyze_sentiment(article_ids: list[int], force_update: bool = False):
    """
    Analyze sentiment for multiple articles in batch.

    Args:
        article_ids: List of article IDs to analyze
        force_update: Whether to force update existing sentiment data

    Returns:
        Dictionary with batch processing results
    """
    try:
        results = []
        success_count = 0
        error_count = 0

        for article_id in article_ids:
            try:
                result = analyze_article_sentiment.delay(article_id, force_update)
                # Wait for result (with timeout)
                task_result = result.get(timeout=30)
                results.append(task_result)

                if task_result["status"] == "completed":
                    success_count += 1
                else:
                    error_count += 1

            except Exception as e:
                logger.error(f"Error processing article {article_id}: {e}")
                error_count += 1
                results.append(
                    {
                        "article_id": article_id,
                        "status": "error",
                        "error": str(e),
                    },
                )

        logger.info(
            f"Batch sentiment analysis completed: "
            f"{success_count} successful, {error_count} errors",
        )

        return {
            "total_articles": len(article_ids),
            "success_count": success_count,
            "error_count": error_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error in batch sentiment analysis: {e}")
        return {
            "total_articles": len(article_ids),
            "success_count": 0,
            "error_count": len(article_ids),
            "error": str(e),
        }


@shared_task(bind=True, max_retries=3)
def update_search_vector(self, article_id: int):
    """
    Update search vector for a single article.

    Args:
        article_id: ID of the article to update

    Returns:
        Dictionary with update results
    """
    try:
        from .models import Article

        article = Article.objects.get(id=article_id)
        article.update_search_vector()

        logger.info(f"Updated search vector for article {article_id}")

        return {
            "article_id": article_id,
            "status": "completed",
            "title": article.title[:100],
        }

    except Article.DoesNotExist:
        logger.error(f"Article {article_id} not found")
        return {
            "article_id": article_id,
            "status": "error",
            "error": "Article not found",
        }
    except Exception as e:
        logger.error(f"Error updating search vector for article {article_id}: {e}")
        # Retry on failure
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=30 * (2**self.request.retries))
        return {
            "article_id": article_id,
            "status": "error",
            "error": str(e),
        }


@shared_task
def batch_update_search_vectors(article_ids: list[int] | None = None):
    """
    Update search vectors for multiple articles or all articles without vectors.

    Args:
        article_ids: List of article IDs to update (optional)

    Returns:
        Dictionary with batch update results
    """
    try:
        from .models import Article

        if article_ids:
            articles = Article.objects.filter(id__in=article_ids)
            total_count = len(article_ids)
        else:
            # Update articles without search vectors
            articles = Article.objects.filter(search_vector__isnull=True)
            total_count = articles.count()

        if total_count == 0:
            return {
                "total_articles": 0,
                "updated_count": 0,
                "message": "No articles need search vector updates",
            }

        updated_count = 0
        for article in articles:
            try:
                article.update_search_vector()
                updated_count += 1

                # Log progress for large batches
                if updated_count % 100 == 0:
                    logger.info(
                        f"Updated search vectors for {updated_count}/{total_count} articles",
                    )

            except Exception as e:
                logger.error(
                    f"Error updating search vector for article {article.id}: {e}",
                )

        logger.info(
            f"Batch search vector update completed: {updated_count}/{total_count} articles",
        )

        return {
            "total_articles": total_count,
            "updated_count": updated_count,
            "success_rate": (updated_count / total_count * 100)
            if total_count > 0
            else 0,
        }

    except Exception as e:
        logger.error(f"Error in batch search vector update: {e}")
        return {
            "total_articles": 0,
            "updated_count": 0,
            "error": str(e),
        }


@shared_task(bind=True, max_retries=3)
def summarize_article(self, article_id: int, summary_type: str = "extractive"):
    """
    Generate summary for an article.

    Args:
        article_id: ID of the article to summarize
        summary_type: 'extractive' or 'abstractive'

    Returns:
        Dictionary with summarization results
    """
    try:
        from .models import Article
        from .summarizer import ArticleSummarizer

        article = Article.objects.get(id=article_id)

        # Skip if already has summary
        if article.summary and article.summary.strip():
            logger.info(f"Article {article_id} already has summary")
            return {
                "article_id": article_id,
                "status": "skipped",
                "summary_length": len(article.summary),
            }

        # Initialize summarizer
        summarizer = ArticleSummarizer(use_transformers=(summary_type == "abstractive"))

        # Generate summary
        summary_result = summarizer.summarize_article(article, summary_type)

        # Update article with summary
        with transaction.atomic():
            article.summary = summary_result["summary"]
            article.save(update_fields=["summary"])

        logger.info(
            f"Generated {summary_type} summary for article {article_id}: "
            f"{len(summary_result['summary'])} characters",
        )

        return {
            "article_id": article_id,
            "status": "completed",
            "summary_type": summary_result["summary_type"],
            "summary_length": summary_result["summary_length"],
            "compression_ratio": summary_result["compression_ratio"],
            "keywords": summary_result["keywords"],
        }

    except Article.DoesNotExist:
        logger.error(f"Article {article_id} not found")
        return {
            "article_id": article_id,
            "status": "error",
            "error": "Article not found",
        }
    except Exception as e:
        logger.error(f"Error summarizing article {article_id}: {e}")
        # Retry on failure
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2**self.request.retries))
        return {
            "article_id": article_id,
            "status": "error",
            "error": str(e),
        }


@shared_task
def process_new_article(article_id: int):
    """
    Process a newly scraped article with all analysis tasks.

    Args:
        article_id: ID of the article to process

    Returns:
        Dictionary with processing results
    """
    try:
        from .models import Article

        article = Article.objects.get(id=article_id)

        results = {
            "article_id": article_id,
            "tasks_completed": [],
            "tasks_failed": [],
        }

        # Update search vector
        try:
            update_search_vector.delay(article_id)
            results["tasks_completed"].append("search_vector")
        except Exception as e:
            logger.error(
                f"Failed to update search vector for article {article_id}: {e}",
            )
            results["tasks_failed"].append(f"search_vector: {e!s}")

        # Analyze sentiment
        try:
            analyze_article_sentiment.delay(article_id)
            results["tasks_completed"].append("sentiment_analysis")
        except Exception as e:
            logger.error(f"Failed to analyze sentiment for article {article_id}: {e}")
            results["tasks_failed"].append(f"sentiment_analysis: {e!s}")

        # Generate summary if content is substantial
        if len(article.content) > 500:
            try:
                summarize_article.delay(article_id)
                results["tasks_completed"].append("summarization")
            except Exception as e:
                logger.error(f"Failed to summarize article {article_id}: {e}")
                results["tasks_failed"].append(f"summarization: {e!s}")

        logger.info(
            f"Initiated processing for article {article_id}: "
            f"{len(results['tasks_completed'])} tasks started",
        )

        return results

    except Article.DoesNotExist:
        logger.error(f"Article {article_id} not found")
        return {
            "article_id": article_id,
            "error": "Article not found",
        }
    except Exception as e:
        logger.error(f"Error processing new article {article_id}: {e}")
        return {
            "article_id": article_id,
            "error": str(e),
        }


@shared_task
def cleanup_search_analytics():
    """
    Clean up old search analytics data.

    Removes search analytics older than 90 days to prevent database bloat.
    """
    try:
        from .models import SearchAnalytics

        # Delete analytics older than 90 days
        cutoff_date = timezone.now() - timedelta(days=90)
        deleted_count = SearchAnalytics.objects.filter(
            created__lt=cutoff_date,
        ).delete()[0]

        logger.info(f"Cleaned up {deleted_count} old search analytics records")

        return {
            "deleted_count": deleted_count,
            "cutoff_date": cutoff_date.isoformat(),
        }

    except Exception as e:
        logger.error(f"Error cleaning up search analytics: {e}")
        return {
            "deleted_count": 0,
            "error": str(e),
        }


@shared_task
def refresh_trending_cache():
    """
    Refresh cached trending articles and search terms.

    This task should be run periodically to update trending content.
    """
    try:
        # Clear trending-related cache keys
        cache_keys = [
            "trending_articles_24h",
            "trending_articles_7d",
            "trending_searches_24h",
            "trending_searches_7d",
        ]

        for key in cache_keys:
            cache.delete(key)

        logger.info("Refreshed trending content cache")

        return {
            "status": "completed",
            "cache_keys_cleared": len(cache_keys),
        }

    except Exception as e:
        logger.error(f"Error refreshing trending cache: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
