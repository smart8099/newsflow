"""
Personalized feed view for recommendations app.
"""

import logging

from django.core.cache import cache
from django.core.paginator import Paginator
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from newsflow.news.serializers import ArticleSerializer

from ..analytics import UserPreferenceAnalyzer
from ..hybrid import HybridRecommender

logger = logging.getLogger(__name__)


class PersonalizedFeedView(APIView):
    """
    API endpoint for personalized article recommendations.

    GET /api/recommendations/feed/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get personalized article feed for the authenticated user.

        Query Parameters:
        - limit: Number of articles (default: 20, max: 50)
        - page: Page number for pagination (default: 1)
        - exclude_read: Whether to exclude read articles (default: true)
        - refresh: Force refresh cache (default: false)

        Returns:
        - articles: List of recommended articles
        - pagination: Pagination metadata
        - user_insights: Basic user reading insights
        """
        try:
            # Parse query parameters
            limit = min(int(request.GET.get("limit", 20)), 50)
            page = int(request.GET.get("page", 1))
            exclude_read = request.GET.get("exclude_read", "true").lower() == "true"
            refresh = request.GET.get("refresh", "false").lower() == "true"

            user_id = request.user.id

            # Check cache first (unless refresh requested)
            cache_key = f"personalized_feed_{user_id}_{limit}_{exclude_read}"
            if not refresh:
                cached_feed = cache.get(cache_key)
                if cached_feed:
                    # Apply pagination to cached results
                    paginator = Paginator(cached_feed, limit)
                    page_obj = paginator.get_page(page)

                    return Response(
                        {
                            "articles": ArticleSerializer(page_obj, many=True).data,
                            "pagination": {
                                "current_page": page,
                                "total_pages": paginator.num_pages,
                                "total_articles": paginator.count,
                                "has_next": page_obj.has_next(),
                                "has_previous": page_obj.has_previous(),
                            },
                            "cached": True,
                            "user_insights": self._get_basic_insights(user_id),
                        },
                    )

            # Generate fresh recommendations
            hybrid_recommender = HybridRecommender()
            recommended_articles = hybrid_recommender.get_personalized_feed(
                user_id=user_id,
                limit=limit * 3,  # Get more for pagination
                exclude_read=exclude_read,
                use_cache=not refresh,
            )

            if not recommended_articles:
                return Response(
                    {
                        "articles": [],
                        "pagination": {
                            "current_page": 1,
                            "total_pages": 0,
                            "total_articles": 0,
                            "has_next": False,
                            "has_previous": False,
                        },
                        "message": "No recommendations available. Try reading some articles first!",
                        "user_insights": self._get_basic_insights(user_id),
                    },
                )

            # Cache the results
            cache.set(cache_key, recommended_articles, 1800)  # 30 minutes

            # Apply pagination
            paginator = Paginator(recommended_articles, limit)
            page_obj = paginator.get_page(page)

            # Serialize articles
            serialized_articles = []
            for article in page_obj:
                article_data = ArticleSerializer(article).data
                article_data["relevance_score"] = getattr(
                    article,
                    "relevance_score",
                    0.0,
                )
                article_data["recommendation_reason"] = getattr(
                    article,
                    "recommendation_reason",
                    "Recommended for you",
                )
                # Add score breakdown if available
                if hasattr(article, "score_breakdown"):
                    article_data["score_breakdown"] = article.score_breakdown

                serialized_articles.append(article_data)

            return Response(
                {
                    "articles": serialized_articles,
                    "pagination": {
                        "current_page": page,
                        "total_pages": paginator.num_pages,
                        "total_articles": paginator.count,
                        "has_next": page_obj.has_next(),
                        "has_previous": page_obj.has_previous(),
                    },
                    "cached": False,
                    "user_insights": self._get_basic_insights(user_id),
                },
            )

        except Exception as e:
            logger.error(
                f"Error generating personalized feed for user {request.user.id}: {e}",
            )
            return Response(
                {"error": "Failed to generate recommendations"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _get_basic_insights(self, user_id: int) -> dict:
        """Get basic user insights for the feed response."""
        try:
            analyzer = UserPreferenceAnalyzer()
            analytics = analyzer.analyze_reading_patterns(user_id, days=7)

            return {
                "articles_read_this_week": analytics["total_articles_read"],
                "reading_streak": analytics.get("reading_streak", 0),
                "favorite_category": analytics.get("favorite_category", {}).get("name"),
                "engagement_rate": round(analytics.get("engagement_rate", 0), 1),
            }
        except Exception:
            return {}
