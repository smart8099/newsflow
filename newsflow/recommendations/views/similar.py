"""
Similar articles view for recommendations app.
"""

import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from newsflow.news.models import Article
from newsflow.news.serializers import ArticleSerializer

from ..engine import ContentBasedRecommender
from ..hybrid import HybridRecommender

logger = logging.getLogger(__name__)


class SimilarArticlesView(APIView):
    """
    API endpoint for similar articles.

    GET /api/recommendations/similar/<article_id>/
    """

    @method_decorator(cache_page(1800))  # Cache for 30 minutes
    @method_decorator(vary_on_headers("Authorization"))
    def get(self, request, article_id):
        """
        Get articles similar to the specified article.

        URL Parameters:
        - article_id: ID of the reference article

        Query Parameters:
        - limit: Number of similar articles (default: 5, max: 10)

        Returns:
        - similar_articles: List of similar articles
        - reference_article: Basic info about the reference article
        """
        try:
            limit = min(int(request.GET.get("limit", 5)), 10)

            # Check if reference article exists
            try:
                reference_article = Article.objects.select_related(
                    "source",
                    "category",
                ).get(id=article_id)
            except Article.DoesNotExist:
                return Response(
                    {"error": "Article not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Get similar articles
            if request.user.is_authenticated:
                hybrid_recommender = HybridRecommender()
                similar_articles = hybrid_recommender.get_similar_articles_blend(
                    article_id,
                    request.user.id,
                    limit,
                )
            else:
                content_recommender = ContentBasedRecommender()
                similar_articles = content_recommender.get_similar_articles(
                    article_id,
                    limit,
                )

            # Serialize results
            serialized_similar = []
            for article in similar_articles:
                article_data = ArticleSerializer(article).data
                article_data["relevance_score"] = getattr(
                    article,
                    "relevance_score",
                    0.0,
                )
                article_data["recommendation_reason"] = getattr(
                    article,
                    "recommendation_reason",
                    "Similar content",
                )
                serialized_similar.append(article_data)

            return Response(
                {
                    "similar_articles": serialized_similar,
                    "reference_article": {
                        "id": reference_article.id,
                        "title": reference_article.title,
                        "category": reference_article.category.name,
                        "source": reference_article.source.name,
                    },
                    "count": len(serialized_similar),
                },
            )

        except Exception as e:
            logger.error(f"Error getting similar articles for {article_id}: {e}")
            return Response(
                {"error": "Failed to get similar articles"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
