"""
Django REST Framework serializers for news models.
"""

from rest_framework import serializers

from .models import Article
from .models import Category
from .models import NewsSource
from .models import UserInteraction


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for Category model."""

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "color"]


class NewsSourceSerializer(serializers.ModelSerializer):
    """Serializer for NewsSource model."""

    class Meta:
        model = NewsSource
        fields = ["id", "name", "base_url", "country", "language"]


class ArticleSerializer(serializers.ModelSerializer):
    """Serializer for Article model."""

    category = CategorySerializer(read_only=True)
    source = NewsSourceSerializer(read_only=True)
    category_names = serializers.CharField(source="get_category_names", read_only=True)
    engagement_score = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            "id",
            "uuid",
            "title",
            "url",
            "summary",
            "author",
            "published_at",
            "read_time",
            "view_count",
            "sentiment_label",
            "sentiment_confidence",
            "top_image",
            "keywords",
            "category",
            "source",
            "category_names",
            "engagement_score",
            "is_recent",
            "is_trending",
        ]

    def get_engagement_score(self, obj):
        """Get engagement score for the article."""
        return getattr(obj, "engagement_score", obj.get_engagement_score())


class ArticleDetailSerializer(ArticleSerializer):
    """Detailed serializer for Article model including content."""

    similar_articles = serializers.SerializerMethodField()

    class Meta(ArticleSerializer.Meta):
        fields = ArticleSerializer.Meta.fields + ["content", "similar_articles"]

    def get_similar_articles(self, obj):
        """Get similar articles for this article."""
        similar = obj.get_similar(limit=5)
        return ArticleSerializer(similar, many=True).data


class UserInteractionSerializer(serializers.ModelSerializer):
    """Serializer for UserInteraction model."""

    article = ArticleSerializer(read_only=True)

    class Meta:
        model = UserInteraction
        fields = [
            "id",
            "uuid",
            "interaction_type",
            "reading_time",
            "created_at",
            "article",
        ]
