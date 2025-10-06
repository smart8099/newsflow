"""
Category-based filtering for NewsFlow recommendations.

This module provides filters for trending content and fresh articles
based on user engagement metrics and categories.
"""

import logging
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count
from django.db.models import F
from django.db.models import Q
from django.db.models import QuerySet
from django.utils import timezone

from newsflow.news.models import Article
from newsflow.news.models import Category
from newsflow.news.models import UserInteraction
from newsflow.users.models import UserProfile

logger = logging.getLogger(__name__)


class CategoryBasedFilter:
    """
    Filter articles based on categories, trends, and freshness.

    Provides methods to get trending articles, fresh content,
    and category-specific recommendations.
    """

    def __init__(self, cache_timeout: int = 900):
        """
        Initialize the category-based filter.

        Args:
            cache_timeout: Cache timeout in seconds (default: 15 minutes)
        """
        self.cache_timeout = cache_timeout

    def get_trending_in_category(
        self,
        category_id: int,
        limit: int = 10,
        time_window: int = 24,
    ) -> QuerySet:
        """
        Get most engaged articles in a category.

        Engagement score = views + (likes * 2) + (shares * 3)

        Args:
            category_id: Category ID to filter by
            limit: Maximum number of articles
            time_window: Time window in hours to consider

        Returns:
            QuerySet of trending articles in the category
        """
        cache_key = f"trending_category_{category_id}_{limit}_{time_window}"
        cached_result = cache.get(cache_key)

        if cached_result:
            return cached_result

        # Calculate cutoff time
        cutoff_time = timezone.now() - timedelta(hours=time_window)

        # Aggregate engagement metrics
        articles = (
            Article.objects.filter(
                categories__id=category_id,
                published_at__gte=cutoff_time,
            )
            .annotate(
                recent_views=Count(
                    "interactions",
                    filter=Q(
                        interactions__action=UserInteraction.ActionType.VIEW,
                        interactions__created_at__gte=cutoff_time,
                    ),
                ),
                recent_likes=Count(
                    "interactions",
                    filter=Q(
                        interactions__action=UserInteraction.ActionType.LIKE,
                        interactions__created_at__gte=cutoff_time,
                    ),
                ),
                recent_shares=Count(
                    "interactions",
                    filter=Q(
                        interactions__action=UserInteraction.ActionType.SHARE,
                        interactions__created_at__gte=cutoff_time,
                    ),
                ),
                engagement_score=F("recent_views")
                + (F("recent_likes") * 2)
                + (F("recent_shares") * 3),
            )
            .filter(
                engagement_score__gt=0,  # Only articles with engagement
            )
            .order_by(
                "-engagement_score",
                "-published_at",
            )
            .select_related(
                "source",
            )
            .prefetch_related("categories")[:limit]
        )

        # Add metadata
        for article in articles:
            article.relevance_score = min(
                1.0,
                article.engagement_score / 100,
            )  # Normalize score
            categories = article.categories.all()
            category_name = categories[0].name if categories else "articles"
            article.recommendation_reason = f"Trending in {category_name}"

        # Cache the result
        cache.set(cache_key, articles, self.cache_timeout)

        logger.info(
            f"Found {len(articles)} trending articles in category {category_id}",
        )
        return articles

    def get_trending_globally(
        self,
        limit: int = 10,
        time_window: int = 24,
        exclude_categories: list[int] | None = None,
    ) -> QuerySet:
        """
        Get globally trending articles across all categories.

        Args:
            limit: Maximum number of articles
            time_window: Time window in hours
            exclude_categories: List of category IDs to exclude

        Returns:
            QuerySet of globally trending articles
        """
        cache_key = f"trending_global_{limit}_{time_window}"
        cached_result = cache.get(cache_key)

        if cached_result and not exclude_categories:
            return cached_result

        cutoff_time = timezone.now() - timedelta(hours=time_window)

        # Base queryset
        queryset = Article.objects.filter(published_at__gte=cutoff_time)

        # Exclude categories if specified
        if exclude_categories:
            queryset = queryset.exclude(categories__id__in=exclude_categories)

        # Calculate engagement
        articles = (
            queryset.annotate(
                recent_views=Count(
                    "interactions",
                    filter=Q(
                        interactions__action=UserInteraction.ActionType.VIEW,
                        interactions__created_at__gte=cutoff_time,
                    ),
                ),
                recent_likes=Count(
                    "interactions",
                    filter=Q(
                        interactions__action=UserInteraction.ActionType.LIKE,
                        interactions__created_at__gte=cutoff_time,
                    ),
                ),
                recent_shares=Count(
                    "interactions",
                    filter=Q(
                        interactions__action=UserInteraction.ActionType.SHARE,
                        interactions__created_at__gte=cutoff_time,
                    ),
                ),
                recent_comments=Count(
                    "interactions",
                    filter=Q(
                        interactions__action=UserInteraction.ActionType.COMMENT,
                        interactions__created_at__gte=cutoff_time,
                    ),
                ),
                engagement_score=(
                    F("recent_views")
                    + (F("recent_likes") * 2)
                    + (F("recent_shares") * 3)
                    + (F("recent_comments") * 2)
                ),
            )
            .filter(
                engagement_score__gt=0,
            )
            .order_by(
                "-engagement_score",
                "-published_at",
            )
            .select_related(
                "source",
            )
            .prefetch_related("categories")[: limit * 2]
        )  # Get extra for diversity filtering

        # Apply source diversity
        diverse_articles = self._apply_source_diversity(articles, limit)

        # Add metadata
        for article in diverse_articles:
            article.relevance_score = min(1.0, article.engagement_score / 200)
            article.recommendation_reason = "Trending now"

        # Cache if no exclusions
        if not exclude_categories:
            cache.set(cache_key, diverse_articles, self.cache_timeout)

        return diverse_articles

    def get_fresh_content(
        self,
        user_id: int,
        limit: int = 10,
        hours_fresh: int = 12,
    ) -> QuerySet:
        """
        Get newest articles in user's preferred categories.

        Args:
            user_id: User ID to get fresh content for
            limit: Maximum number of articles
            hours_fresh: How many hours to consider as "fresh"

        Returns:
            QuerySet of fresh articles
        """
        cache_key = f"fresh_content_{user_id}_{limit}_{hours_fresh}"
        cached_result = cache.get(cache_key)

        if cached_result:
            return cached_result

        cutoff_time = timezone.now() - timedelta(hours=hours_fresh)

        # Get user preferences
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
            preferred_categories = user_profile.preferred_categories.all()

            if preferred_categories:
                queryset = Article.objects.filter(
                    categories__in=preferred_categories,
                    published_at__gte=cutoff_time,
                )
            else:
                # No preferences, get from all categories
                queryset = Article.objects.filter(published_at__gte=cutoff_time)

        except UserProfile.DoesNotExist:
            # No profile, get from all categories
            queryset = Article.objects.filter(published_at__gte=cutoff_time)

        # Exclude already viewed articles
        viewed_ids = UserInteraction.objects.filter(
            user_id=user_id,
            action=UserInteraction.ActionType.VIEW,
        ).values_list("article_id", flat=True)

        articles = (
            queryset.exclude(
                id__in=viewed_ids,
            )
            .order_by(
                "-published_at",
            )
            .select_related(
                "source",
            )
            .prefetch_related("categories")[:limit]
        )

        # Add metadata
        for article in articles:
            # Freshness score based on how recent
            hours_old = (timezone.now() - article.published_at).total_seconds() / 3600
            freshness_score = max(0, 1 - (hours_old / hours_fresh))
            article.relevance_score = freshness_score
            article.recommendation_reason = f"Fresh from {article.source.name}"

        # Cache the result
        cache.set(cache_key, articles, self.cache_timeout)

        logger.info(f"Found {len(articles)} fresh articles for user {user_id}")
        return articles

    def get_category_recommendations(
        self,
        user_id: int,
        limit: int = 10,
        exclude_read: bool = True,
    ) -> QuerySet:
        """
        Get recommendations based purely on user's category preferences.

        Args:
            user_id: User ID
            limit: Maximum number of articles
            exclude_read: Whether to exclude read articles

        Returns:
            QuerySet of articles from preferred categories
        """
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
            preferred_categories = user_profile.preferred_categories.all()

            if not preferred_categories:
                # Analyze user's reading history to infer preferences
                preferred_categories = self._infer_category_preferences(user_id)

            if not preferred_categories:
                # Still no preferences, return diverse content
                return self._get_diverse_recommendations(limit, exclude_read, user_id)

            # Get articles from preferred categories
            queryset = Article.objects.filter(
                categories__in=preferred_categories,
            )

            if exclude_read:
                viewed_ids = UserInteraction.objects.filter(
                    user_id=user_id,
                    action=UserInteraction.ActionType.VIEW,
                ).values_list("article_id", flat=True)
                queryset = queryset.exclude(id__in=viewed_ids)

            # Mix trending and fresh
            cutoff_recent = timezone.now() - timedelta(days=3)

            articles = (
                queryset.filter(
                    published_at__gte=cutoff_recent,
                )
                .annotate(
                    interaction_count=Count("interactions"),
                )
                .order_by(
                    "-interaction_count",
                    "-published_at",
                )
                .select_related(
                    "source",
                )
                .prefetch_related("categories")[:limit]
            )

            # Add metadata
            for article in articles:
                article.relevance_score = 0.7
                categories = article.categories.all()
                category_name = (
                    categories[0].name if categories else "various categories"
                )
                article.recommendation_reason = f"From {category_name}"

            return articles

        except UserProfile.DoesNotExist:
            return self._get_diverse_recommendations(limit, exclude_read, user_id)

    def get_breaking_news(self, limit: int = 5, minutes: int = 60) -> QuerySet:
        """
        Get breaking news articles published very recently.

        Args:
            limit: Maximum number of articles
            minutes: How many minutes to consider as breaking

        Returns:
            QuerySet of breaking news articles
        """
        cache_key = f"breaking_news_{limit}_{minutes}"
        cached_result = cache.get(cache_key)

        if cached_result:
            return cached_result

        cutoff_time = timezone.now() - timedelta(minutes=minutes)

        articles = (
            Article.objects.filter(
                published_at__gte=cutoff_time,
            )
            .annotate(
                early_engagement=Count(
                    "interactions",
                    filter=Q(interactions__created_at__gte=cutoff_time),
                ),
            )
            .order_by(
                "-early_engagement",
                "-published_at",
            )
            .select_related(
                "source",
            )
            .prefetch_related("categories")[:limit]
        )

        # Add metadata
        for article in articles:
            article.relevance_score = 1.0  # Breaking news gets high relevance
            article.recommendation_reason = "Breaking news"

        # Cache for short time
        cache.set(cache_key, articles, 300)  # 5 minutes

        return articles

    def _apply_source_diversity(self, articles: QuerySet, limit: int) -> list[Article]:
        """
        Apply source diversity to prevent single source dominance.

        Args:
            articles: QuerySet of articles
            limit: Maximum number to return

        Returns:
            List of diverse articles
        """
        diverse_articles = []
        source_counts = {}
        max_per_source = 2

        for article in articles:
            source_id = article.source_id
            count = source_counts.get(source_id, 0)

            if count < max_per_source:
                diverse_articles.append(article)
                source_counts[source_id] = count + 1

                if len(diverse_articles) >= limit:
                    break

        return diverse_articles

    def _infer_category_preferences(self, user_id: int) -> list[Category]:
        """
        Infer user's category preferences from reading history.

        Args:
            user_id: User ID

        Returns:
            List of inferred preferred categories
        """
        # Get user's reading history
        category_stats = (
            UserInteraction.objects.filter(
                user_id=user_id,
                action__in=[
                    UserInteraction.ActionType.VIEW,
                    UserInteraction.ActionType.LIKE,
                ],
            )
            .values(
                "article__category",
            )
            .annotate(
                interaction_count=Count("id"),
            )
            .order_by("-interaction_count")[:5]
        )

        if not category_stats:
            return []

        category_ids = [
            stat["article__category"]
            for stat in category_stats
            if stat["article__category"]
        ]
        return list(Category.objects.filter(id__in=category_ids))

    def _get_diverse_recommendations(
        self,
        limit: int,
        exclude_read: bool,
        user_id: int,
    ) -> QuerySet:
        """
        Get diverse recommendations when no preferences are available.

        Args:
            limit: Maximum number of articles
            exclude_read: Whether to exclude read articles
            user_id: User ID

        Returns:
            QuerySet of diverse articles
        """
        queryset = Article.objects.all()

        if exclude_read:
            viewed_ids = UserInteraction.objects.filter(
                user_id=user_id,
                action=UserInteraction.ActionType.VIEW,
            ).values_list("article_id", flat=True)
            queryset = queryset.exclude(id__in=viewed_ids)

        # Get mix of trending and recent
        cutoff_recent = timezone.now() - timedelta(days=2)

        articles = (
            queryset.filter(
                published_at__gte=cutoff_recent,
            )
            .annotate(
                interaction_count=Count("interactions"),
            )
            .order_by(
                "-interaction_count",
                "-published_at",
            )
            .select_related(
                "source",
            )
            .prefetch_related("categories")[: limit * 2]
        )

        # Apply diversity
        diverse_articles = self._apply_source_diversity(articles, limit)

        # Add metadata
        for article in diverse_articles:
            article.relevance_score = 0.6
            article.recommendation_reason = "Popular article"

        return diverse_articles
