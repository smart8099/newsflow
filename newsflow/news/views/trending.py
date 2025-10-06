"""
Trending views for news app.
"""

from datetime import timedelta

from django.db import models
from django.db.models import Count
from django.utils import timezone
from django.views.generic import TemplateView

from ..models import Article
from ..models import CategoryChoices


class TrendingView(TemplateView):
    """
    Trending articles view showing popular content from the last 24 hours.
    """

    template_name = "news/trending.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get trending articles from last 24 hours
        trending_24h = (
            Article.objects.published()
            .filter(
                published_at__gte=timezone.now() - timedelta(hours=24),
            )
            .select_related("source")
            .prefetch_related("categories")
            .order_by(
                "-view_count",
                "-published_at",
            )[:20]
        )

        # Top trending article
        top_trending = trending_24h.first() if trending_24h else None

        # Calculate total views for today
        total_views = (
            Article.objects.published()
            .filter(
                published_at__gte=timezone.now() - timedelta(hours=24),
            )
            .aggregate(
                total=models.Sum("view_count"),
            )["total"]
            or 0
        )

        # Calculate growth compared to yesterday
        yesterday_views = (
            Article.objects.published()
            .filter(
                published_at__gte=timezone.now() - timedelta(hours=48),
                published_at__lt=timezone.now() - timedelta(hours=24),
            )
            .aggregate(
                total=models.Sum("view_count"),
            )["total"]
            or 1
        )

        growth_percentage = (
            ((total_views - yesterday_views) / yesterday_views) * 100
            if yesterday_views > 0
            else 0
        )

        # Trending categories (by view count)
        trending_categories = (
            Article.objects.published()
            .filter(
                published_at__gte=timezone.now() - timedelta(hours=24),
            )
            .values("source__primary_category")
            .annotate(
                view_count=models.Sum("view_count"),
            )
            .filter(
                source__primary_category__isnull=False,
            )
            .order_by("-view_count")[:8]
        )

        # Map category codes to display names
        category_choices = dict(CategoryChoices.choices)
        for item in trending_categories:
            item["category"] = category_choices.get(
                item["source__primary_category"],
                item["source__primary_category"].title(),
            )

        # Trending search terms (if available)
        trending_searches = []
        try:
            from ..models import SearchAnalytics

            trending_searches = (
                SearchAnalytics.objects.filter(
                    created__gte=timezone.now() - timedelta(hours=24),
                    result_count__gt=0,
                )
                .values("normalized_query")
                .annotate(
                    search_count=Count("id"),
                )
                .order_by("-search_count")[:10]
            )
        except:
            pass

        context.update(
            {
                "trending_articles": trending_24h,
                "trending_24h": trending_24h,  # For template compatibility
                "featured_article": top_trending,
                "total_views": total_views,
                "growth_percentage": growth_percentage,
                "trending_categories": trending_categories,
                "trending_searches": trending_searches,
            },
        )

        return context
