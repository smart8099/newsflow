"""
Hybrid recommendation system for NewsFlow.

Combines content-based, category-based, and collaborative filtering
strategies to provide comprehensive personalized recommendations.
"""

import logging
from collections import defaultdict

from django.core.cache import cache
from django.db.models import QuerySet

from newsflow.news.models import Article
from newsflow.users.models import UserProfile

from .engine import ContentBasedRecommender
from .filters import CategoryBasedFilter

logger = logging.getLogger(__name__)


class HybridRecommender:
    """
    Hybrid recommendation system combining multiple strategies.

    Blends content-based (60%), category trending (30%), and fresh content (10%)
    to provide diverse and relevant recommendations.
    """

    def __init__(
        self,
        content_weight: float = 0.6,
        trending_weight: float = 0.3,
        fresh_weight: float = 0.1,
        cache_timeout: int = 1800,
    ):
        """
        Initialize the hybrid recommender.

        Args:
            content_weight: Weight for content-based recommendations
            trending_weight: Weight for trending recommendations
            fresh_weight: Weight for fresh content
            cache_timeout: Cache timeout in seconds (default: 30 minutes)
        """
        # Validate weights sum to 1
        total_weight = content_weight + trending_weight + fresh_weight
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(f"Weights don't sum to 1.0: {total_weight}. Normalizing.")
            content_weight /= total_weight
            trending_weight /= total_weight
            fresh_weight /= total_weight

        self.content_weight = content_weight
        self.trending_weight = trending_weight
        self.fresh_weight = fresh_weight
        self.cache_timeout = cache_timeout

        # Initialize component recommenders
        self.content_recommender = ContentBasedRecommender()
        self.category_filter = CategoryBasedFilter()

    def get_personalized_feed(
        self,
        user_id: int,
        limit: int = 20,
        exclude_read: bool = True,
        use_cache: bool = True,
    ) -> list[Article]:
        """
        Get personalized article feed for a user.

        Blends multiple recommendation strategies to create
        a diverse and relevant feed.

        Args:
            user_id: User ID to get feed for
            limit: Maximum number of articles
            exclude_read: Whether to exclude read articles
            use_cache: Whether to use cached results

        Returns:
            List of recommended articles with scores and reasons
        """
        cache_key = f"hybrid_feed_{user_id}_{limit}_{exclude_read}"

        if use_cache:
            cached_feed = cache.get(cache_key)
            if cached_feed:
                logger.info(f"Returning cached feed for user {user_id}")
                return cached_feed

        # Collect recommendations from each strategy
        recommendations = {}

        # 1. Content-based recommendations
        content_recs = self._get_content_recommendations(
            user_id,
            limit * 2,
            exclude_read,
        )
        for article in content_recs:
            recommendations[article.id] = {
                "article": article,
                "content_score": article.relevance_score * self.content_weight,
                "trending_score": 0,
                "fresh_score": 0,
                "reasons": [article.recommendation_reason],
            }

        # 2. Trending recommendations
        trending_recs = self._get_trending_recommendations(
            user_id,
            limit,
            exclude_read,
        )
        for article in trending_recs:
            if article.id in recommendations:
                recommendations[article.id]["trending_score"] = (
                    article.relevance_score * self.trending_weight
                )
                if (
                    article.recommendation_reason
                    not in recommendations[article.id]["reasons"]
                ):
                    recommendations[article.id]["reasons"].append(
                        article.recommendation_reason,
                    )
            else:
                recommendations[article.id] = {
                    "article": article,
                    "content_score": 0,
                    "trending_score": article.relevance_score * self.trending_weight,
                    "fresh_score": 0,
                    "reasons": [article.recommendation_reason],
                }

        # 3. Fresh content
        fresh_recs = self._get_fresh_recommendations(
            user_id,
            limit,
            exclude_read,
        )
        for article in fresh_recs:
            if article.id in recommendations:
                recommendations[article.id]["fresh_score"] = (
                    article.relevance_score * self.fresh_weight
                )
                if (
                    article.recommendation_reason
                    not in recommendations[article.id]["reasons"]
                ):
                    recommendations[article.id]["reasons"].append(
                        article.recommendation_reason,
                    )
            else:
                recommendations[article.id] = {
                    "article": article,
                    "content_score": 0,
                    "trending_score": 0,
                    "fresh_score": article.relevance_score * self.fresh_weight,
                    "reasons": [article.recommendation_reason],
                }

        # Calculate combined scores
        for article_id, rec_data in recommendations.items():
            rec_data["total_score"] = (
                rec_data["content_score"]
                + rec_data["trending_score"]
                + rec_data["fresh_score"]
            )

        # Sort by total score
        sorted_recs = sorted(
            recommendations.values(),
            key=lambda x: x["total_score"],
            reverse=True,
        )

        # Apply diversity and limit
        diverse_feed = self._apply_diversity_constraints(sorted_recs, limit)

        # Prepare final feed
        final_feed = []
        for rec_data in diverse_feed:
            article = rec_data["article"]
            article.relevance_score = rec_data["total_score"]
            article.recommendation_reason = self._format_reasons(rec_data["reasons"])

            # Add score breakdown for debugging
            article.score_breakdown = {
                "content": rec_data["content_score"],
                "trending": rec_data["trending_score"],
                "fresh": rec_data["fresh_score"],
                "total": rec_data["total_score"],
            }

            final_feed.append(article)

        # Cache the feed
        if use_cache:
            cache.set(cache_key, final_feed, self.cache_timeout)

        logger.info(
            f"Generated hybrid feed for user {user_id}: "
            f"{len(final_feed)} articles from {len(recommendations)} candidates",
        )

        return final_feed

    def get_explore_feed(
        self,
        user_id: int | None = None,
        limit: int = 20,
    ) -> list[Article]:
        """
        Get an exploration feed with diverse content.

        Focuses on discovery of new topics and sources.

        Args:
            user_id: Optional user ID for personalization
            limit: Maximum number of articles

        Returns:
            List of diverse articles for exploration
        """
        cache_key = f"explore_feed_{user_id}_{limit}"
        cached_feed = cache.get(cache_key)

        if cached_feed:
            return cached_feed

        explore_feed = []

        # Get breaking news
        breaking = self.category_filter.get_breaking_news(limit=5)
        explore_feed.extend(breaking)

        # Get globally trending
        trending = self.category_filter.get_trending_globally(
            limit=limit // 2,
            time_window=48,
        )
        explore_feed.extend(trending)

        # If user is logged in, add some personalized content
        if user_id:
            # Get articles from categories the user hasn't explored much
            unexplored = self._get_unexplored_categories(user_id, limit=5)
            explore_feed.extend(unexplored)

        # Remove duplicates and limit
        seen_ids = set()
        unique_feed = []
        for article in explore_feed:
            if article.id not in seen_ids:
                seen_ids.add(article.id)
                unique_feed.append(article)
                if len(unique_feed) >= limit:
                    break

        # Cache the feed
        cache.set(cache_key, unique_feed, 600)  # 10 minutes

        return unique_feed

    def get_similar_articles_blend(
        self,
        article_id: int,
        user_id: int | None = None,
        limit: int = 8,
    ) -> list[Article]:
        """
        Get similar articles with optional personalization.

        Args:
            article_id: Reference article ID
            user_id: Optional user ID for personalization
            limit: Maximum number of articles

        Returns:
            List of similar articles
        """
        # Get content-based similar articles
        similar = self.content_recommender.get_similar_articles(
            article_id,
            limit=limit,
        )

        # If user is logged in, boost articles from preferred sources
        if user_id:
            try:
                user_profile = UserProfile.objects.get(user_id=user_id)
                preferred_sources = user_profile.preferred_sources.all()

                for article in similar:
                    if article.source in preferred_sources:
                        article.relevance_score *= 1.2  # Boost by 20%
                        article.recommendation_reason += " (from your preferred source)"

                # Re-sort after boosting
                similar = sorted(similar, key=lambda a: a.relevance_score, reverse=True)

            except UserProfile.DoesNotExist:
                pass

        return list(similar)[:limit]

    def _get_content_recommendations(
        self,
        user_id: int,
        limit: int,
        exclude_read: bool,
    ) -> QuerySet:
        """Get content-based recommendations."""
        try:
            return self.content_recommender.get_recommendations(
                user_id,
                limit,
                exclude_read,
            )
        except Exception as e:
            logger.error(f"Error getting content recommendations: {e}")
            return []

    def _get_trending_recommendations(
        self,
        user_id: int,
        limit: int,
        exclude_read: bool,
    ) -> list[Article]:
        """Get trending recommendations based on user preferences."""
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
            preferred_categories = user_profile.preferred_categories.all()

            if not preferred_categories:
                # Get globally trending
                return list(self.category_filter.get_trending_globally(limit=limit))

            # Get trending from preferred categories
            trending_articles = []
            per_category = max(2, limit // len(preferred_categories))

            for category in preferred_categories:
                category_trending = self.category_filter.get_trending_in_category(
                    category.id,
                    limit=per_category,
                )
                trending_articles.extend(category_trending)

            # Sort by engagement and limit
            trending_articles.sort(
                key=lambda a: getattr(a, "engagement_score", 0),
                reverse=True,
            )

            return trending_articles[:limit]

        except UserProfile.DoesNotExist:
            # Fallback to global trending
            return list(self.category_filter.get_trending_globally(limit=limit))
        except Exception as e:
            logger.error(f"Error getting trending recommendations: {e}")
            return []

    def _get_fresh_recommendations(
        self,
        user_id: int,
        limit: int,
        exclude_read: bool,
    ) -> QuerySet:
        """Get fresh content recommendations."""
        try:
            return self.category_filter.get_fresh_content(
                user_id,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting fresh recommendations: {e}")
            return []

    def _apply_diversity_constraints(
        self,
        recommendations: list[dict],
        limit: int,
    ) -> list[dict]:
        """
        Apply diversity constraints to recommendations.

        Ensures:
        - No more than 3 articles from same source
        - No more than 4 articles from same category
        - Mix of content types

        Args:
            recommendations: List of recommendation data dicts
            limit: Maximum number to return

        Returns:
            Diverse list of recommendations
        """
        diverse_recs = []
        source_counts = defaultdict(int)
        category_counts = defaultdict(int)

        max_per_source = 3
        max_per_category = 4

        for rec_data in recommendations:
            article = rec_data["article"]

            # Check source constraint
            if source_counts[article.source_id] >= max_per_source:
                continue

            # Check category constraint
            if category_counts[article.category_id] >= max_per_category:
                continue

            # Add to diverse list
            diverse_recs.append(rec_data)
            source_counts[article.source_id] += 1
            category_counts[article.category_id] += 1

            if len(diverse_recs) >= limit:
                break

        # If we don't have enough after diversity, add more lenient constraints
        if len(diverse_recs) < limit:
            for rec_data in recommendations:
                if rec_data not in diverse_recs:
                    diverse_recs.append(rec_data)
                    if len(diverse_recs) >= limit:
                        break

        return diverse_recs

    def _get_unexplored_categories(
        self,
        user_id: int,
        limit: int,
    ) -> list[Article]:
        """
        Get articles from categories the user hasn't explored much.

        Args:
            user_id: User ID
            limit: Maximum number of articles

        Returns:
            List of articles from unexplored categories
        """
        from django.db.models import Count

        from newsflow.news.models import Category
        from newsflow.news.models import UserInteraction

        # Get user's category interaction counts
        user_categories = (
            UserInteraction.objects.filter(
                user_id=user_id,
            )
            .values("article__category")
            .annotate(
                interaction_count=Count("id"),
            )
            .order_by("interaction_count")
        )

        # Get least explored categories
        explored_category_ids = [c["article__category"] for c in user_categories]

        # Get categories not explored or least explored
        unexplored_categories = Category.objects.exclude(
            id__in=explored_category_ids[: len(explored_category_ids) // 2],
        )

        if not unexplored_categories:
            unexplored_categories = Category.objects.all()

        # Get recent articles from these categories
        articles = Article.objects.filter(
            category__in=unexplored_categories,
        ).order_by("-published_at")[:limit]

        for article in articles:
            article.relevance_score = 0.5
            article.recommendation_reason = f"Explore {article.category.name}"

        return list(articles)

    def _format_reasons(self, reasons: list[str]) -> str:
        """
        Format multiple recommendation reasons into a single string.

        Args:
            reasons: List of reason strings

        Returns:
            Formatted reason string
        """
        if not reasons:
            return "Recommended for you"

        # Remove duplicates while preserving order
        seen = set()
        unique_reasons = []
        for reason in reasons:
            if reason not in seen:
                seen.add(reason)
                unique_reasons.append(reason)

        if len(unique_reasons) == 1:
            return unique_reasons[0]
        if len(unique_reasons) == 2:
            return f"{unique_reasons[0]} and {unique_reasons[1]}"
        return f"{unique_reasons[0]}, {unique_reasons[1]}, and more"
