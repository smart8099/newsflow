import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView

from newsflow.news.models import NewsSource
from newsflow.scrapers.services import NewsScraperService
from newsflow.scrapers.tasks import health_check_sources
from newsflow.scrapers.tasks import scrape_all_active_sources
from newsflow.scrapers.tasks import scrape_single_article
from newsflow.scrapers.tasks import scrape_single_source

logger = logging.getLogger(__name__)


class ScrapingAPIView(View):
    """Base API view for scraping operations."""

    @method_decorator(login_required)
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        """Ensure user is authenticated for all scraping operations."""
        return super().dispatch(request, *args, **kwargs)

    def json_response(self, data: dict, status: int = 200) -> JsonResponse:
        """Return JSON response with consistent format."""
        return JsonResponse(data, status=status)

    def error_response(self, message: str, status: int = 400) -> JsonResponse:
        """Return error response."""
        return self.json_response({"error": message, "success": False}, status=status)

    def success_response(self, data: dict = None, message: str = None) -> JsonResponse:
        """Return success response."""
        response_data = {"success": True}
        if data:
            response_data.update(data)
        if message:
            response_data["message"] = message
        return self.json_response(response_data)


class ScrapeSourceAPIView(ScrapingAPIView):
    """API endpoint to trigger scraping for a specific source."""

    def post(self, request, source_id):
        """Trigger scraping for a news source."""
        try:
            source = NewsSource.objects.get(id=source_id, is_active=True)
        except NewsSource.DoesNotExist:
            return self.error_response(
                f"Active news source with ID {source_id} not found",
                404,
            )

        try:
            # Check if source is due for scraping
            force_scrape = request.POST.get("force", "false").lower() == "true"

            if not force_scrape and not source.is_due_for_scraping:
                return self.error_response(
                    f'Source "{source.name}" is not due for scraping yet. '
                    f"Next scrape scheduled for {source.next_scrape_time}",
                    400,
                )

            # Queue scraping task
            result = scrape_single_source.delay(source.id)

            return self.success_response(
                {
                    "task_id": result.id,
                    "source_name": source.name,
                    "source_id": source.id,
                    "message": f'Scraping task queued for "{source.name}"',
                },
            )

        except Exception as e:
            logger.error(f"Failed to queue scraping task for source {source_id}: {e}")
            return self.error_response(f"Failed to queue scraping task: {e!s}", 500)


class ScrapeAllSourcesAPIView(ScrapingAPIView):
    """API endpoint to trigger scraping for all active sources."""

    def post(self, request):
        """Trigger scraping for all due sources."""
        try:
            # Check how many sources are due
            sources_due = NewsSource.objects.needs_scraping()

            if not sources_due:
                return self.success_response(
                    {
                        "sources_due": 0,
                        "message": "No sources are due for scraping",
                    },
                )

            # Queue bulk scraping task
            result = scrape_all_active_sources.delay()

            return self.success_response(
                {
                    "task_id": result.id,
                    "sources_due": len(sources_due),
                    "source_names": [
                        source.name for source in sources_due[:10]
                    ],  # First 10
                    "message": f"Bulk scraping task queued for {len(sources_due)} sources",
                },
            )

        except Exception as e:
            logger.error(f"Failed to queue bulk scraping task: {e}")
            return self.error_response(
                f"Failed to queue bulk scraping task: {e!s}",
                500,
            )


class ScrapeArticleAPIView(ScrapingAPIView):
    """API endpoint to scrape a single article from URL."""

    def post(self, request):
        """Scrape a single article from provided URL."""
        url = request.POST.get("url")
        if not url:
            return self.error_response("URL parameter is required")

        source_id = request.POST.get("source_id")
        test_mode = request.POST.get("test_mode", "false").lower() == "true"

        try:
            if test_mode:
                # Synchronous scraping for testing
                scraper = NewsScraperService()
                article_data = scraper.scrape_article(url)

                if not article_data:
                    return self.error_response("Failed to scrape article")

                # Validate quality
                is_valid, reason = scraper.validate_article_quality(article_data)

                return self.success_response(
                    {
                        "article": {
                            "title": article_data["title"],
                            "author": article_data["author"],
                            "published_at": article_data["published_at"].isoformat()
                            if article_data["published_at"]
                            else None,
                            "content_length": len(article_data["content"]),
                            "keywords": article_data["keywords"][:5],
                            "read_time": article_data["read_time"],
                            "summary": article_data["summary"][:200] + "..."
                            if len(article_data["summary"]) > 200
                            else article_data["summary"],
                        },
                        "quality_check": {
                            "is_valid": is_valid,
                            "reason": reason,
                        },
                        "test_mode": True,
                    },
                )
            # Asynchronous scraping
            result = scrape_single_article.delay(url, source_id)

            return self.success_response(
                {
                    "task_id": result.id,
                    "url": url,
                    "message": "Article scraping task queued",
                },
            )

        except Exception as e:
            logger.error(f"Failed to scrape article {url}: {e}")
            return self.error_response(f"Failed to scrape article: {e!s}", 500)


class HealthCheckAPIView(ScrapingAPIView):
    """API endpoint to perform health checks on news sources."""

    def post(self, request):
        """Trigger health check for all sources."""
        try:
            result = health_check_sources.delay()

            return self.success_response(
                {
                    "task_id": result.id,
                    "message": "Health check task queued for all sources",
                },
            )

        except Exception as e:
            logger.error(f"Failed to queue health check: {e}")
            return self.error_response(f"Failed to queue health check: {e!s}", 500)


class ScrapingStatusAPIView(ScrapingAPIView):
    """API endpoint to get scraping status and statistics."""

    def get(self, request):
        """Get current scraping status and statistics."""
        try:
            scraper = NewsScraperService()

            # Get global statistics
            global_stats = scraper.get_scraping_statistics()

            # Get sources due for scraping
            sources_due = NewsSource.objects.needs_scraping()

            # Get recent activity
            recent_articles = []
            try:
                from newsflow.news.models import Article

                articles = Article.objects.select_related("source").order_by(
                    "-scraped_at",
                )[:5]
                recent_articles = [
                    {
                        "title": article.title,
                        "source_name": article.source.name,
                        "scraped_at": article.scraped_at.isoformat(),
                        "url": article.url,
                    }
                    for article in articles
                ]
            except Exception:
                pass

            # Get source-specific stats
            source_stats = []
            active_sources = NewsSource.objects.active()[:10]  # First 10 active sources
            for source in active_sources:
                source_stats.append(
                    {
                        "id": source.id,
                        "name": source.name,
                        "is_due_for_scraping": source.is_due_for_scraping,
                        "last_scraped": source.last_scraped.isoformat()
                        if source.last_scraped
                        else None,
                        "success_rate": source.success_rate,
                        "total_articles": source.total_articles_scraped,
                        "next_scrape_time": source.next_scrape_time.isoformat()
                        if source.next_scrape_time
                        else None,
                    },
                )

            return self.success_response(
                {
                    "global_stats": global_stats,
                    "sources_due_count": len(sources_due),
                    "sources_due": [
                        {"id": source.id, "name": source.name}
                        for source in sources_due[:5]  # First 5
                    ],
                    "recent_articles": recent_articles,
                    "source_stats": source_stats,
                    "timestamp": timezone.now().isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"Failed to get scraping status: {e}")
            return self.error_response(f"Failed to get scraping status: {e!s}", 500)


class SourceStatsAPIView(ScrapingAPIView):
    """API endpoint to get statistics for a specific source."""

    def get(self, request, source_id):
        """Get detailed statistics for a specific news source."""
        try:
            source = NewsSource.objects.get(id=source_id)
        except NewsSource.DoesNotExist:
            return self.error_response(
                f"News source with ID {source_id} not found",
                404,
            )

        try:
            scraper = NewsScraperService()
            stats = scraper.get_scraping_statistics(source_id)

            # Add additional source details
            stats.update(
                {
                    "source_details": {
                        "name": source.name,
                        "source_type": source.source_type,
                        "base_url": source.base_url,
                        "rss_feed": source.rss_feed,
                        "is_active": source.is_active,
                        "scrape_frequency": source.scrape_frequency,
                        "max_articles_per_scrape": source.max_articles_per_scrape,
                        "primary_category": source.primary_category,
                        "country": source.country,
                        "language": source.language,
                        "credibility_score": source.credibility_score,
                        "bias_rating": source.bias_rating,
                    },
                },
            )

            return self.success_response(stats)

        except Exception as e:
            logger.error(f"Failed to get source stats for {source_id}: {e}")
            return self.error_response(f"Failed to get source statistics: {e!s}", 500)


# Function-based API views for simpler endpoints
@require_http_methods(["GET"])
@login_required
def list_sources_api(request):
    """API endpoint to list all news sources."""
    try:
        sources = NewsSource.objects.all().values(
            "id",
            "name",
            "source_type",
            "is_active",
            "last_scraped",
            "total_articles_scraped",
            "success_rate",
            "primary_category",
        )

        return JsonResponse(
            {
                "success": True,
                "sources": list(sources),
                "count": sources.count(),
            },
        )

    except Exception as e:
        logger.error(f"Failed to list sources: {e}")
        return JsonResponse(
            {
                "success": False,
                "error": f"Failed to list sources: {e!s}",
            },
            status=500,
        )


@require_http_methods(["POST"])
@login_required
@csrf_exempt
def toggle_source_status_api(request, source_id):
    """API endpoint to activate/deactivate a news source."""
    try:
        source = NewsSource.objects.get(id=source_id)
    except NewsSource.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "error": f"News source with ID {source_id} not found",
            },
            status=404,
        )

    try:
        # Toggle active status
        source.is_active = not source.is_active
        source.save(update_fields=["is_active"])

        return JsonResponse(
            {
                "success": True,
                "source_id": source.id,
                "source_name": source.name,
                "is_active": source.is_active,
                "message": f'Source "{source.name}" {"activated" if source.is_active else "deactivated"}',
            },
        )

    except Exception as e:
        logger.error(f"Failed to toggle source status for {source_id}: {e}")
        return JsonResponse(
            {
                "success": False,
                "error": f"Failed to toggle source status: {e!s}",
            },
            status=500,
        )


# Dashboard view
class ScrapingDashboardView(TemplateView):
    """Dashboard view for scraping management."""

    template_name = "scrapers/dashboard.html"

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            scraper = NewsScraperService()
            stats = scraper.get_scraping_statistics()

            # Get sources due for scraping
            sources_due = NewsSource.objects.needs_scraping()

            # Get recent articles
            recent_articles = []
            try:
                from newsflow.news.models import Article

                recent_articles = Article.objects.select_related("source").order_by(
                    "-scraped_at",
                )[:10]
            except Exception:
                pass

            context.update(
                {
                    "stats": stats,
                    "sources_due": sources_due,
                    "recent_articles": recent_articles,
                    "active_sources_count": NewsSource.objects.active().count(),
                    "total_sources_count": NewsSource.objects.count(),
                },
            )

        except Exception as e:
            logger.error(f"Failed to get dashboard context: {e}")
            context["error"] = str(e)

        return context
