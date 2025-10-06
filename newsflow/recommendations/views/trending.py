"""
Trending articles view for recommendations app.
"""

import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from newsflow.news.models import Category
from newsflow.news.serializers import ArticleSerializer

from ..filters import CategoryBasedFilter

logger = logging.getLogger(__name__)


class TrendingView(APIView):
    """
    API endpoint for trending articles.

    GET /api/recommendations/trending/
    """

    @method_decorator(cache_page(900))  # Cache for 15 minutes
    def get(self, request):
        """
        Get trending articles globally or by category.

        Query Parameters:
        - category_id: Filter by category (optional)
        - limit: Number of articles (default: 10, max: 20)
        - time_window: Hours to consider for trending (default: 24, max: 168)

        Returns:
        - trending_articles: List of trending articles
        - category: Category info if filtered
        - time_window: Time window used
        """
        try:
            category_id = request.GET.get("category_id")
            limit = min(int(request.GET.get("limit", 10)), 20)
            time_window = min(int(request.GET.get("time_window", 24)), 168)

            category_filter = CategoryBasedFilter()

            if category_id:
                # Category-specific trending
                try:
                    category = Category.objects.get(id=category_id)
                    trending_articles = category_filter.get_trending_in_category(
                        category_id,
                        limit,
                        time_window,
                    )
                    category_info = {
                        "id": category.id,
                        "name": category.name,
                        "description": category.description,
                    }
                except Category.DoesNotExist:
                    return Response(
                        {"error": "Category not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
            else:
                # Global trending
                trending_articles = category_filter.get_trending_globally(
                    limit,
                    time_window,
                )
                category_info = None

            # Serialize articles
            serialized_articles = []
            for article in trending_articles:
                article_data = ArticleSerializer(article).data
                article_data["relevance_score"] = getattr(
                    article,
                    "relevance_score",
                    0.0,
                )
                article_data["recommendation_reason"] = getattr(
                    article,
                    "recommendation_reason",
                    "Trending now",
                )
                # Add engagement metrics if available
                if hasattr(article, "engagement_score"):
                    article_data["engagement_score"] = article.engagement_score
                if hasattr(article, "recent_views"):
                    article_data["recent_views"] = article.recent_views

                serialized_articles.append(article_data)

            return Response(
                {
                    "trending_articles": serialized_articles,
                    "category": category_info,
                    "time_window_hours": time_window,
                    "count": len(serialized_articles),
                },
            )

        except Exception as e:
            logger.error(f"Error getting trending articles: {e}")
            return Response(
                {"error": "Failed to get trending articles"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
