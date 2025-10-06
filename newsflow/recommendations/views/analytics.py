"""
Analytics views for recommendations app.
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from newsflow.news.models import Article

from ..analytics import UserPreferenceAnalyzer
from ..tasks import trigger_user_recommendation_update

logger = logging.getLogger(__name__)


class UserAnalyticsView(APIView):
    """
    API endpoint for user analytics and insights.

    GET /api/recommendations/analytics/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get detailed analytics for the authenticated user.

        Query Parameters:
        - days: Number of days to analyze (default: 30, max: 90)

        Returns:
        - reading_patterns: Detailed reading analytics
        - insights: Actionable insights and recommendations
        - category_affinity: User's category preferences
        """
        try:
            days = min(int(request.GET.get("days", 30)), 90)
            user_id = request.user.id

            analyzer = UserPreferenceAnalyzer()

            # Get comprehensive analytics
            reading_patterns = analyzer.analyze_reading_patterns(user_id, days)
            insights = analyzer.get_user_insights(user_id)
            category_affinity = analyzer.get_category_affinity(user_id)

            return Response(
                {
                    "reading_patterns": reading_patterns,
                    "insights": insights,
                    "category_affinity": [
                        {"category": cat, "affinity": round(score, 3)}
                        for cat, score in category_affinity
                    ],
                    "analysis_period_days": days,
                },
            )

        except Exception as e:
            logger.error(f"Error getting user analytics for {request.user.id}: {e}")
            return Response(
                {"error": "Failed to get user analytics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def record_interaction(request):
    """
    Record user interaction and trigger recommendation updates.

    POST /api/recommendations/interaction/

    Body:
    - article_id: ID of the article
    - interaction_type: Type of interaction (view, like, share, etc.)
    - reading_time: Time spent reading (for view interactions)
    """
    try:
        article_id = request.data.get("article_id")
        interaction_type = request.data.get("interaction_type")
        reading_time = request.data.get("reading_time")

        if not article_id or not interaction_type:
            return Response(
                {"error": "article_id and interaction_type are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate article exists
        try:
            Article.objects.get(id=article_id)
        except Article.DoesNotExist:
            return Response(
                {"error": "Article not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create interaction record
        from newsflow.news.models import UserInteraction

        interaction = UserInteraction.objects.create(
            user_id=request.user.id,
            article_id=article_id,
            interaction_type=interaction_type,
            reading_time=reading_time,
        )

        # Trigger recommendation update in background
        trigger_user_recommendation_update.delay(
            request.user.id,
            interaction_type,
        )

        return Response(
            {
                "success": True,
                "interaction_id": interaction.id,
                "message": "Interaction recorded successfully",
            },
        )

    except Exception as e:
        logger.error(f"Error recording interaction: {e}")
        return Response(
            {"error": "Failed to record interaction"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
