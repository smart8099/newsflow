import logging

from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import path
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

logger = logging.getLogger(__name__)


class ScrapingAdminMixin:
    """Mixin to add scraping functionality to admin interfaces."""

    def get_urls(self):
        """Add custom admin URLs for scraping actions."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "scraping-dashboard/",
                self.admin_site.admin_view(self.scraping_dashboard_view),
                name="scrapers_scraping_dashboard",
            ),
            path(
                "scrape-source/<int:source_id>/",
                self.admin_site.admin_view(self.scrape_source_view),
                name="scrapers_scrape_source",
            ),
            path(
                "health-check/",
                self.admin_site.admin_view(self.health_check_view),
                name="scrapers_health_check",
            ),
        ]
        return custom_urls + urls

    def scraping_dashboard_view(self, request):
        """Custom view for scraping dashboard."""
        from django.shortcuts import render

        from newsflow.scrapers.services import NewsScraperService

        try:
            from newsflow.news.models import Article
            from newsflow.news.models import NewsSource

            scraper = NewsScraperService()
            stats = scraper.get_scraping_statistics()

            # Get sources due for scraping
            sources_due = NewsSource.objects.needs_scraping()

            # Get recent scraping activity
            recent_articles = Article.objects.select_related("source").order_by(
                "-scraped_at",
            )[:10]

            context = {
                "title": "News Scraping Dashboard",
                "stats": stats,
                "sources_due": sources_due,
                "recent_articles": recent_articles,
                "opts": self.model._meta,
                "has_view_permission": True,
            }

        except ImportError:
            context = {
                "title": "News Scraping Dashboard",
                "error": "NewsSource model not available",
                "opts": self.model._meta,
                "has_view_permission": True,
            }

        return render(request, "admin/scrapers/scraping_dashboard.html", context)

    def scrape_source_view(self, request, source_id):
        """Trigger scraping for a specific source."""
        try:
            from newsflow.news.models import NewsSource
            from newsflow.scrapers.tasks import scrape_single_source

            source = NewsSource.objects.get(id=source_id)

            # Queue scraping task
            result = scrape_single_source.delay(source_id)

            messages.success(
                request,
                f'Scraping task queued for "{source.name}". Task ID: {result.id}',
            )

        except ImportError:
            messages.error(request, "NewsSource model not available.")
        except Exception as e:
            try:
                from newsflow.news.models import NewsSource

                messages.error(request, f"NewsSource with ID {source_id} not found.")
            except ImportError:
                messages.error(request, f"Failed to queue scraping task: {e}")

        return HttpResponseRedirect(reverse("admin:scrapers_scraping_dashboard"))

    def health_check_view(self, request):
        """Trigger health check for all sources."""
        try:
            from newsflow.scrapers.tasks import health_check_sources

            result = health_check_sources.delay()
            messages.success(
                request,
                f"Health check task queued. Task ID: {result.id}",
            )
        except Exception as e:
            messages.error(request, f"Failed to queue health check: {e}")

        return HttpResponseRedirect(reverse("admin:scrapers_scraping_dashboard"))


# Enhance the existing NewsSource admin
class EnhancedNewsSourceAdmin(ScrapingAdminMixin, admin.ModelAdmin):
    """Enhanced admin interface for NewsSource with scraping controls."""

    list_display = [
        "name",
        "source_type",
        "is_active",
        "scraping_status_display",
        "last_scraped_display",
        "total_articles_scraped",
        "success_rate_display",
        "scrape_actions",
    ]

    list_filter = [
        "source_type",
        "is_active",
        "primary_category",
        "country",
        "language",
        "last_scraped",
    ]

    search_fields = ["name", "base_url", "description"]

    readonly_fields = [
        "uuid",
        "slug",
        "last_scraped",
        "total_articles_scraped",
        "success_rate",
        "average_response_time",
        "next_scrape_time_display",
        "articles_count_display",
    ]

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "uuid",
                    "name",
                    "slug",
                    "description",
                ),
            },
        ),
        (
            "URLs and Configuration",
            {
                "fields": (
                    "base_url",
                    "rss_feed",
                    "api_endpoint",
                    "source_type",
                ),
            },
        ),
        (
            "Content Settings",
            {
                "fields": (
                    "primary_category",
                    "country",
                    "language",
                    "is_active",
                ),
            },
        ),
        (
            "Scraping Configuration",
            {
                "fields": (
                    "scrape_frequency",
                    "max_articles_per_scrape",
                    "custom_selectors",
                    "headers",
                ),
            },
        ),
        (
            "Quality and Performance",
            {
                "fields": (
                    "credibility_score",
                    "bias_rating",
                ),
            },
        ),
        (
            "Statistics (Read-only)",
            {
                "fields": (
                    "last_scraped",
                    "total_articles_scraped",
                    "success_rate",
                    "average_response_time",
                    "next_scrape_time_display",
                    "articles_count_display",
                ),
            },
        ),
    )

    actions = [
        "scrape_selected_sources",
        "activate_sources",
        "deactivate_sources",
        "reset_scraping_stats",
    ]

    def scraping_status_display(self, obj):
        """Display scraping status with visual indicators."""
        if not obj.is_active:
            return format_html(
                '<span style="color: #999;">⏸️ Inactive</span>',
            )

        if obj.is_due_for_scraping:
            return format_html(
                '<span style="color: #e74c3c;">🔴 Due for scraping</span>',
            )

        next_scrape = obj.next_scrape_time
        if next_scrape:
            time_until = next_scrape - timezone.now()
            if time_until.total_seconds() < 3600:  # Less than 1 hour
                return format_html(
                    '<span style="color: #f39c12;">🟡 Soon ({} min)</span>',
                    int(time_until.total_seconds() / 60),
                )

        return format_html(
            '<span style="color: #27ae60;">🟢 Up to date</span>',
        )

    scraping_status_display.short_description = "Status"

    def last_scraped_display(self, obj):
        """Display last scraped time in a user-friendly format."""
        if not obj.last_scraped:
            return format_html('<span style="color: #999;">Never</span>')

        time_ago = timezone.now() - obj.last_scraped
        if time_ago.days > 0:
            return format_html(
                '<span title="{}">{} days ago</span>',
                obj.last_scraped.strftime("%Y-%m-%d %H:%M"),
                time_ago.days,
            )
        if time_ago.seconds > 3600:
            hours = time_ago.seconds // 3600
            return format_html(
                '<span title="{}">{} hours ago</span>',
                obj.last_scraped.strftime("%Y-%m-%d %H:%M"),
                hours,
            )
        minutes = time_ago.seconds // 60
        return format_html(
            '<span title="{}">{} minutes ago</span>',
            obj.last_scraped.strftime("%Y-%m-%d %H:%M"),
            minutes or 1,
        )

    last_scraped_display.short_description = "Last Scraped"

    def success_rate_display(self, obj):
        """Display success rate with color coding."""
        rate = obj.success_rate or 0

        if rate >= 90:
            color = "#27ae60"  # Green
        elif rate >= 70:
            color = "#f39c12"  # Orange
        else:
            color = "#e74c3c"  # Red

        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color,
            rate,
        )

    success_rate_display.short_description = "Success Rate"

    def scrape_actions(self, obj):
        """Display action buttons for each source."""
        if not obj.is_active:
            return format_html('<span style="color: #999;">Inactive</span>')

        scrape_url = reverse("admin:scrapers_scrape_source", args=[obj.id])

        return format_html(
            '<a class="button" href="{}">Scrape Now</a>',
            scrape_url,
        )

    scrape_actions.short_description = "Actions"

    def next_scrape_time_display(self, obj):
        """Display next scheduled scrape time."""
        if not obj.is_active:
            return "Source inactive"

        next_time = obj.next_scrape_time
        if next_time:
            return next_time.strftime("%Y-%m-%d %H:%M:%S")
        return "Unknown"

    next_scrape_time_display.short_description = "Next Scrape Time"

    def articles_count_display(self, obj):
        """Display article counts with breakdown."""
        try:
            total = obj.total_articles_scraped
            last_24h = obj.get_articles_count_last_24h()

            return format_html(
                "Total: {} | Last 24h: {}",
                total,
                last_24h,
            )
        except Exception:
            return f"Total: {obj.total_articles_scraped}"

    articles_count_display.short_description = "Articles"

    def scrape_selected_sources(self, request, queryset):
        """Bulk action to scrape selected sources."""
        active_sources = queryset.filter(is_active=True)

        if not active_sources:
            messages.warning(request, "No active sources selected.")
            return

        queued_count = 0
        for source in active_sources:
            try:
                scrape_single_source.delay(source.id)
                queued_count += 1
            except Exception as e:
                messages.error(
                    request,
                    f"Failed to queue scraping for {source.name}: {e}",
                )

        if queued_count:
            messages.success(
                request,
                f"Queued scraping tasks for {queued_count} sources.",
            )

    scrape_selected_sources.short_description = "Scrape selected sources"

    def activate_sources(self, request, queryset):
        """Bulk action to activate sources."""
        updated = queryset.update(is_active=True)
        messages.success(request, f"Activated {updated} sources.")

    activate_sources.short_description = "Activate selected sources"

    def deactivate_sources(self, request, queryset):
        """Bulk action to deactivate sources."""
        updated = queryset.update(is_active=False)
        messages.success(request, f"Deactivated {updated} sources.")

    deactivate_sources.short_description = "Deactivate selected sources"

    def reset_scraping_stats(self, request, queryset):
        """Bulk action to reset scraping statistics."""
        with transaction.atomic():
            updated = queryset.update(
                total_articles_scraped=0,
                success_rate=100.0,
                average_response_time=None,
                last_scraped=None,
            )

        messages.success(request, f"Reset statistics for {updated} sources.")

    reset_scraping_stats.short_description = "Reset scraping statistics"

    def changelist_view(self, request, extra_context=None):
        """Add dashboard link to changelist view."""
        extra_context = extra_context or {}
        extra_context["dashboard_url"] = reverse("admin:scrapers_scraping_dashboard")
        return super().changelist_view(request, extra_context)


# Register the enhanced admin when the module loads
def register_enhanced_admin():
    """Register enhanced NewsSource admin."""
    try:
        from django.contrib import admin

        from newsflow.news.models import NewsSource

        # Check if NewsSource is already registered and unregister it
        if NewsSource in admin.site._registry:
            admin.site.unregister(NewsSource)

        # Register enhanced admin
        admin.site.register(NewsSource, EnhancedNewsSourceAdmin)

    except ImportError:
        # Models might not be available yet
        pass
    except Exception as e:
        logger.warning(f"Failed to register enhanced admin: {e}")


# Try to register when module loads
register_enhanced_admin()
