"""
Search views for news app.
"""

import time
from datetime import timedelta

from django.db.models import Count
from django.db.models import Q
from django.utils import timezone
from django.views.generic import ListView

from ..models import Article
from ..models import SearchAnalytics


class SearchResultsView(ListView):
    """
    Search results view with advanced filtering and facets.
    """

    model = Article
    template_name = "news/search_results.html"
    context_object_name = "articles"
    paginate_by = 15

    def get_queryset(self):
        self.start_time = time.time()  # Store start time for analytics

        query = self.request.GET.get("q", "").strip()
        if not query:
            return Article.objects.none()

        # Use existing search functionality
        search_type = self.request.GET.get("search_type", "phrase")
        if search_type in ["phrase", "plain", "web"]:
            articles = Article.objects.advanced_search(query, search_type)
        else:
            articles = Article.objects.search(query)

        # Apply filters
        category = self.request.GET.get("category")
        if category:
            articles = articles.filter(
                Q(source__primary_category=category) | Q(categories__slug=category),
            )

        sentiment = self.request.GET.get("sentiment")
        if sentiment:
            articles = articles.filter(sentiment_label=sentiment)

        source_id = self.request.GET.get("source")
        if source_id:
            articles = articles.filter(source_id=source_id)

        date_from = self.request.GET.get("date_from")
        if date_from:
            articles = articles.filter(published_at__date__gte=date_from)

        date_to = self.request.GET.get("date_to")
        if date_to:
            articles = articles.filter(published_at__date__lte=date_to)

        return articles.select_related("source").prefetch_related("categories")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        search_type = self.request.GET.get("search_type", "phrase")

        # Get search facets for filtering
        base_queryset = self.get_queryset()

        # Category facets
        category_facets = (
            base_queryset.values(
                "source__primary_category",
            )
            .annotate(
                count=Count("id"),
            )
            .filter(
                count__gt=0,
                source__primary_category__isnull=False,
            )
            .order_by("-count")
        )

        # Source facets
        source_facets = (
            base_queryset.values(
                "source__id",
                "source__name",
            )
            .annotate(
                count=Count("id"),
            )
            .filter(
                count__gt=0,
            )
            .order_by("-count")[:10]
        )

        # Sentiment facets
        sentiment_facets = (
            base_queryset.values(
                "sentiment_label",
            )
            .annotate(
                count=Count("id"),
            )
            .filter(
                count__gt=0,
                sentiment_label__isnull=False,
            )
            .order_by("-count")
        )

        # Applied filters for display
        applied_filters = {
            "category": self.request.GET.get("category"),
            "source": self.request.GET.get("source"),
            "sentiment": self.request.GET.get("sentiment"),
            "date_from": self.request.GET.get("date_from"),
            "date_to": self.request.GET.get("date_to"),
        }

        # Trending searches for empty query state
        trending_searches = []
        try:
            from .models import SearchAnalytics

            trending_searches = (
                SearchAnalytics.objects.filter(
                    created__gte=timezone.now() - timedelta(days=7),
                    result_count__gt=0,
                )
                .values("normalized_query")
                .annotate(
                    search_count=Count("id"),
                )
                .order_by("-search_count")[:8]
            )
        except:
            pass

        context.update(
            {
                "query": query,
                "search_type": search_type,
                "category_facets": category_facets,
                "source_facets": source_facets,
                "sentiment_facets": sentiment_facets,
                "applied_filters": applied_filters,
                "trending_searches": trending_searches,
            },
        )

        # Record search analytics with timing
        if query and hasattr(self, "start_time"):
            end_time = time.time()
            response_time_ms = int((end_time - self.start_time) * 1000)

            try:
                # Get paginator to get total result count
                paginator = context.get("paginator")
                result_count = paginator.count if paginator else 0

                # Record comprehensive search analytics
                self._record_search_analytics(
                    query,
                    result_count,
                    response_time_ms,
                    applied_filters,
                )
            except Exception:
                # Don't let analytics recording break the search
                pass

        return context

    def _record_search_analytics(
        self,
        query,
        result_count,
        response_time_ms,
        applied_filters,
    ):
        """Record search analytics for web interface searches."""
        try:
            # Get user information
            user = self.request.user if self.request.user.is_authenticated else None

            # Get client information
            ip_address = self._get_client_ip()
            user_agent = self.request.META.get("HTTP_USER_AGENT", "")[:500]
            session_id = (
                self.request.session.session_key
                if hasattr(self.request, "session")
                else None
            )

            # Use the model's record_search helper method
            SearchAnalytics.record_search(
                query=query,
                result_count=result_count,
                user=user,
                search_type="web",
                filters=applied_filters or {},
                response_time_ms=response_time_ms,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception as e:
            # Don't let analytics recording break the search
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Error recording search analytics: {e}")

    def _get_client_ip(self):
        """Get client IP address from request."""
        x_forwarded_for = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = self.request.META.get("REMOTE_ADDR")
        return ip
