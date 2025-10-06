"""
Search API views for NewsFlow.

Provides endpoints for article search, autocomplete, trending content,
and search analytics.
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Article
from .models import Category
from .models import NewsSource
from .serializers import ArticleSerializer

logger = logging.getLogger(__name__)


class ArticleSearchView(APIView):
    """
    API endpoint for article search.

    GET /api/search/articles/
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """
        Search articles with full-text search and filtering.

        Query Parameters:
        - q: Search query (required)
        - limit: Number of results per page (default: 10, max: 50)
        - page: Page number (default: 1)
        - category: Filter by category ID
        - source: Filter by source ID
        - sentiment: Filter by sentiment (positive, neutral, negative)
        - date_from: Filter articles from date (YYYY-MM-DD)
        - date_to: Filter articles to date (YYYY-MM-DD)
        - sort: Sort order (relevance, date, popularity)
        - search_type: Search type (phrase, plain, web)

        Returns:
        - articles: List of matching articles
        - pagination: Pagination metadata
        - facets: Search facets for filtering
        - query_info: Information about the search
        """
        import time

        # Start timing the search
        start_time = time.time()

        try:
            query = request.GET.get("q", "").strip()
            if not query:
                return Response(
                    {"error": "Search query is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Pagination parameters
            limit = min(int(request.GET.get("limit", 10)), 50)
            page = int(request.GET.get("page", 1))

            # Filter parameters
            category_id = request.GET.get("category")
            source_id = request.GET.get("source")
            sentiment = request.GET.get("sentiment")
            date_from = request.GET.get("date_from")
            date_to = request.GET.get("date_to")
            sort_by = request.GET.get("sort", "relevance")
            search_type = request.GET.get("search_type", "phrase")

            # Check cache first
            cache_key = self._build_cache_key(
                query,
                limit,
                page,
                category_id,
                source_id,
                sentiment,
                date_from,
                date_to,
                sort_by,
                search_type,
            )
            cached_result = cache.get(cache_key)
            if cached_result:
                # Record analytics for cached searches too
                end_time = time.time()
                response_time_ms = int((end_time - start_time) * 1000)
                cached_result["query_info"]["search_time_ms"] = response_time_ms

                self._record_search_analytics(
                    request,
                    query,
                    cached_result["pagination"]["total_results"],
                    response_time_ms,
                    {
                        "cached": True,
                        "category": category_id,
                        "source": source_id,
                        "sentiment": sentiment,
                    },
                )
                return Response(cached_result)

            # Perform search
            if search_type in ["phrase", "plain", "web"]:
                articles = Article.objects.advanced_search(query, search_type)
            else:
                articles = Article.objects.search(query)

            # Apply filters
            articles = self._apply_filters(
                articles,
                category_id,
                source_id,
                sentiment,
                date_from,
                date_to,
            )

            # Apply sorting
            articles = self._apply_sorting(articles, sort_by)

            # Get facets before pagination
            facets = self._get_search_facets(articles)

            # Apply pagination
            paginator = Paginator(articles, limit)
            page_obj = paginator.get_page(page)

            # Calculate response time
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)

            # Serialize results
            serialized_articles = []
            for article in page_obj:
                article_data = ArticleSerializer(article).data
                article_data["relevance_score"] = getattr(article, "rank", 0.0)
                article_data["snippet"] = article.get_snippet(query, 200)
                serialized_articles.append(article_data)

            result = {
                "articles": serialized_articles,
                "pagination": {
                    "current_page": page,
                    "total_pages": paginator.num_pages,
                    "total_results": paginator.count,
                    "has_next": page_obj.has_next(),
                    "has_previous": page_obj.has_previous(),
                },
                "facets": facets,
                "query_info": {
                    "query": query,
                    "search_type": search_type,
                    "total_found": paginator.count,
                    "search_time_ms": response_time_ms,
                },
            }

            # Cache the result for 5 minutes
            cache.set(cache_key, result, 300)

            # Record search analytics for all searches (authenticated and anonymous)
            applied_filters = {
                "category": category_id,
                "source": source_id,
                "sentiment": sentiment,
                "date_from": date_from,
                "date_to": date_to,
                "sort": sort_by,
                "search_type": search_type,
                "cached": False,
            }
            self._record_search_analytics(
                request,
                query,
                paginator.count,
                response_time_ms,
                applied_filters,
            )

            return Response(result)

        except Exception as e:
            logger.error(f"Error in article search: {e}")
            return Response(
                {"error": "Search failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _build_cache_key(
        self,
        query,
        limit,
        page,
        category_id,
        source_id,
        sentiment,
        date_from,
        date_to,
        sort_by,
        search_type,
    ):
        """Build cache key for search results."""
        key_parts = [
            "search_articles",
            str(hash(query)),
            str(limit),
            str(page),
            str(category_id or ""),
            str(source_id or ""),
            str(sentiment or ""),
            str(date_from or ""),
            str(date_to or ""),
            sort_by,
            search_type,
        ]
        return "_".join(key_parts)

    def _apply_filters(
        self,
        queryset,
        category_id,
        source_id,
        sentiment,
        date_from,
        date_to,
    ):
        """Apply filters to the search queryset."""
        if category_id:
            try:
                queryset = queryset.filter(categories__id=category_id)
            except ValueError:
                pass

        if source_id:
            try:
                queryset = queryset.filter(source__id=source_id)
            except ValueError:
                pass

        if sentiment:
            queryset = queryset.filter(sentiment_label=sentiment)

        if date_from:
            try:
                queryset = queryset.filter(published_at__date__gte=date_from)
            except ValueError:
                pass

        if date_to:
            try:
                queryset = queryset.filter(published_at__date__lte=date_to)
            except ValueError:
                pass

        return queryset

    def _apply_sorting(self, queryset, sort_by):
        """Apply sorting to the search queryset."""
        if sort_by == "date":
            return queryset.order_by("-published_at")
        if sort_by == "popularity":
            return queryset.order_by("-view_count", "-published_at")
        # relevance (default)
        # Already ordered by rank in search method
        return queryset

    def _get_search_facets(self, queryset):
        """Get search facets for filtering."""
        try:
            # Category facets
            category_facets = (
                queryset.values(
                    "categories__id",
                    "categories__name",
                )
                .annotate(
                    count=Count("id"),
                )
                .filter(
                    count__gt=0,
                    categories__isnull=False,
                )
                .order_by("-count")[:10]
            )

            # Source facets
            source_facets = (
                queryset.values(
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
                queryset.values(
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

            return {
                "categories": [
                    {
                        "id": item["categories__id"],
                        "name": item["categories__name"],
                        "count": item["count"],
                    }
                    for item in category_facets
                    if item["categories__name"]
                ],
                "sources": [
                    {
                        "id": item["source__id"],
                        "name": item["source__name"],
                        "count": item["count"],
                    }
                    for item in source_facets
                ],
                "sentiments": [
                    {
                        "label": item["sentiment_label"],
                        "count": item["count"],
                    }
                    for item in sentiment_facets
                ],
            }
        except Exception as e:
            logger.warning(f"Error building search facets: {e}")
            return {"categories": [], "sources": [], "sentiments": []}

    def _record_search_analytics(
        self,
        request,
        query,
        result_count,
        response_time_ms=None,
        filters=None,
    ):
        """Record comprehensive search analytics."""
        try:
            from .models import SearchAnalytics

            # Get user information
            user = request.user if request.user.is_authenticated else None

            # Get client information
            ip_address = self._get_client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]  # Limit length
            session_id = (
                request.session.session_key if hasattr(request, "session") else None
            )

            # Use the model's record_search helper method
            SearchAnalytics.record_search(
                query=query,
                result_count=result_count,
                user=user,
                search_type="article",
                filters=filters or {},
                response_time_ms=response_time_ms,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception as e:
            logger.warning(f"Error recording search analytics: {e}")

    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class AutocompleteView(APIView):
    """
    API endpoint for search autocomplete suggestions.

    GET /api/search/autocomplete/
    """

    permission_classes = [AllowAny]

    @method_decorator(cache_page(300))  # Cache for 5 minutes
    def get(self, request):
        """
        Get autocomplete suggestions for search.

        Query Parameters:
        - q: Partial search query (minimum 2 characters)
        - limit: Number of suggestions (default: 5, max: 10)

        Returns:
        - suggestions: List of search suggestions
        """
        try:
            query = request.GET.get("q", "").strip()
            if len(query) < 2:
                return Response({"suggestions": []})

            limit = min(int(request.GET.get("limit", 5)), 10)

            # Get title suggestions
            title_suggestions = Article.objects.autocomplete_search(
                query,
                limit,
            )

            suggestions = [
                {"text": item["title"], "type": "title"} for item in title_suggestions
            ]

            # Add category suggestions if query matches
            category_suggestions = Category.objects.filter(
                name__icontains=query,
                is_active=True,
            ).values("name")[:3]

            for cat in category_suggestions:
                suggestions.append(
                    {
                        "text": cat["name"],
                        "type": "category",
                    },
                )

            # Add source suggestions if query matches
            source_suggestions = NewsSource.objects.filter(
                name__icontains=query,
                is_active=True,
            ).values("name")[:3]

            for source in source_suggestions:
                suggestions.append(
                    {
                        "text": source["name"],
                        "type": "source",
                    },
                )

            # Limit final results
            suggestions = suggestions[:limit]

            return Response({"suggestions": suggestions})

        except Exception as e:
            logger.error(f"Error in autocomplete: {e}")
            return Response(
                {"suggestions": []},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TrendingSearchView(APIView):
    """
    API endpoint for trending search terms.

    GET /api/search/trending/
    """

    permission_classes = [AllowAny]

    @method_decorator(cache_page(900))  # Cache for 15 minutes
    def get(self, request):
        """
        Get trending search terms.

        Query Parameters:
        - limit: Number of trending terms (default: 10, max: 20)
        - time_window: Hours to consider (default: 24, max: 168)

        Returns:
        - trending_terms: List of trending search terms
        - time_window: Time window used
        """
        try:
            limit = min(int(request.GET.get("limit", 10)), 20)
            time_window = min(int(request.GET.get("time_window", 24)), 168)

            # Calculate trending from SearchAnalytics
            since = timezone.now() - timedelta(hours=time_window)

            try:
                from .models import SearchAnalytics

                trending_queries = (
                    SearchAnalytics.objects.filter(
                        created__gte=since,
                        result_count__gt=0,  # Only successful searches
                    )
                    .values("query")
                    .annotate(
                        search_count=Count("id"),
                    )
                    .order_by("-search_count")[:limit]
                )

                trending_terms = [
                    {
                        "term": item["query"],
                        "search_count": item["search_count"],
                    }
                    for item in trending_queries
                ]
            except Exception:
                # Fallback to static trending terms
                trending_terms = [
                    {"term": "technology", "search_count": 0},
                    {"term": "politics", "search_count": 0},
                    {"term": "business", "search_count": 0},
                    {"term": "sports", "search_count": 0},
                    {"term": "health", "search_count": 0},
                ][:limit]

            return Response(
                {
                    "trending_terms": trending_terms,
                    "time_window_hours": time_window,
                    "count": len(trending_terms),
                },
            )

        except Exception as e:
            logger.error(f"Error getting trending searches: {e}")
            return Response(
                {"error": "Failed to get trending searches"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_history(request):
    """
    Get user's search history.

    GET /api/search/history/

    Query Parameters:
    - limit: Number of history items (default: 20, max: 100)

    Returns:
    - search_history: List of user's recent searches
    """
    try:
        limit = min(int(request.GET.get("limit", 20)), 100)

        from .models import SearchAnalytics

        history = (
            SearchAnalytics.objects.filter(
                user=request.user,
            )
            .order_by("-created")
            .values(
                "query",
                "result_count",
                "created",
            )[:limit]
        )

        return Response(
            {
                "search_history": list(history),
                "count": len(history),
            },
        )

    except Exception as e:
        logger.error(f"Error getting search history: {e}")
        return Response(
            {"error": "Failed to get search history"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def clear_search_history(request):
    """
    Clear user's search history.

    DELETE /api/search/history/

    Returns:
    - success: True if cleared successfully
    """
    try:
        from .models import SearchAnalytics

        deleted_count = SearchAnalytics.objects.filter(
            user=request.user,
        ).delete()[0]

        return Response(
            {
                "success": True,
                "deleted_count": deleted_count,
                "message": "Search history cleared successfully",
            },
        )

    except Exception as e:
        logger.error(f"Error clearing search history: {e}")
        return Response(
            {"error": "Failed to clear search history"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
