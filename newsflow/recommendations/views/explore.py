"""
Explore feed view for recommendations app.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from newsflow.news.serializers import ArticleSerializer

from ..hybrid import HybridRecommender

logger = logging.getLogger(__name__)


class ExploreFeedView(APIView):
    """
    API endpoint for exploration feed.

    GET /api/recommendations/explore/
    """

    def get(self, request):
        """
        Get diverse exploration feed for discovery.

        Query Parameters:
        - limit: Number of articles (default: 20, max: 30)

        Returns:
        - explore_articles: List of diverse articles
        - sections: Different sections in the explore feed
        """
        try:
            limit = min(int(request.GET.get("limit", 20)), 30)

            user_id = request.user.id if request.user.is_authenticated else None

            hybrid_recommender = HybridRecommender()
            explore_articles = hybrid_recommender.get_explore_feed(user_id, limit)

            # Group articles by recommendation reason for sections
            sections = {}
            for article in explore_articles:
                reason = getattr(article, "recommendation_reason", "Explore")
                if reason not in sections:
                    sections[reason] = []

                article_data = ArticleSerializer(article).data
                article_data["relevance_score"] = getattr(
                    article,
                    "relevance_score",
                    0.0,
                )
                article_data["recommendation_reason"] = reason

                sections[reason].append(article_data)

            return Response(
                {
                    "explore_articles": [
                        ArticleSerializer(article).data for article in explore_articles
                    ],
                    "sections": sections,
                    "count": len(explore_articles),
                },
            )

        except Exception as e:
            logger.error(f"Error getting explore feed: {e}")
            return Response(
                {"error": "Failed to get explore feed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
