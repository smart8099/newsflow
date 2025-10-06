"""
Home view for news app.
"""

from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count
from django.db.models import Q
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import TemplateView

from ..models import Article
from ..models import CategoryChoices
from ..models import NewsSource
from ..models import SearchAnalytics


class NewsHomeView(TemplateView):
    """
    Main news homepage with Google News-style layout.

    Features:
    - Featured articles section
    - Categorized news sections
    - Trending sidebar
    - Source credibility information
    """

    template_name = "news/index.html"

    def get(self, request, *args, **kwargs):
        """Handle GET requests with potential redirects for filtering."""
        # Check if filtering parameters are provided
        filter_params = [
            "sort",
            "category",
            "sentiment",
            "source",
            "date_from",
            "date_to",
        ]
        has_filters = any(request.GET.get(param) for param in filter_params)

        if has_filters:
            # Redirect to the category 'all' page with the filters
            category = request.GET.get("category", "all")
            if category == "all" or not category:
                redirect_url = "/category/all/"
            else:
                redirect_url = f"/category/{category}/"

            # Preserve all query parameters
            query_string = request.GET.urlencode()
            if query_string:
                redirect_url += f"?{query_string}"

            return redirect(redirect_url)

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Cache key for performance
        cache_key = f"news_home_context_{self.request.user.id or 'anonymous'}"
        cached_context = cache.get(cache_key)

        if cached_context:
            context.update(cached_context)
            return context

        # Featured articles (is_featured=True or high view count)
        featured_articles = (
            Article.objects.published()
            .filter(
                Q(is_featured=True) | Q(view_count__gte=100),
            )
            .select_related("source")
            .prefetch_related("categories")
            .order_by(
                "-is_featured",
                "-view_count",
                "-published_at",
            )[:6]
        )

        # Get articles by category
        categorized_articles = {}
        category_choices = CategoryChoices.choices

        for category_code, category_name in category_choices[
            :6
        ]:  # Limit to 6 categories for homepage
            articles = (
                Article.objects.published()
                .filter(
                    source__primary_category=category_code,
                )
                .select_related("source")
                .prefetch_related("categories")
                .order_by(
                    "-published_at",
                )[:4]
            )  # 4 articles per category

            if articles:
                categorized_articles[category_name] = articles

        # Trending articles (high view count in last 24 hours)
        trending_articles = (
            Article.objects.published()
            .filter(
                published_at__gte=timezone.now() - timedelta(hours=24),
            )
            .order_by("-view_count")[:8]
        )

        # Top sources by credibility
        top_sources = NewsSource.objects.active().order_by(
            "-credibility_score",
            "-total_articles_scraped",
        )[:6]

        # Latest articles for "All News" section
        latest_articles = (
            Article.objects.published()
            .select_related(
                "source",
            )
            .prefetch_related("categories")
            .order_by("-published_at")[:12]
        )

        # Search trending terms (if available)
        trending_searches = []
        try:
            trending_searches = (
                SearchAnalytics.objects.filter(
                    created__gte=timezone.now() - timedelta(days=7),
                    result_count__gt=0,
                )
                .values("normalized_query")
                .annotate(
                    search_count=Count("id"),
                )
                .order_by("-search_count")[:5]
            )
        except:
            pass

        # Sentiment distribution for dashboard
        sentiment_stats = (
            Article.objects.published()
            .exclude(
                sentiment_label__isnull=True,
            )
            .values("sentiment_label")
            .annotate(
                count=Count("id"),
            )
        )

        context_data = {
            "featured_articles": featured_articles,
            "categorized_articles": categorized_articles,
            "trending_articles": trending_articles,
            "top_sources": top_sources,
            "latest_articles": latest_articles,
            "trending_searches": trending_searches,
            "sentiment_stats": sentiment_stats,
            "category_choices": category_choices,
        }

        # Cache for 10 minutes
        cache.set(cache_key, context_data, 600)
        context.update(context_data)
        return context
