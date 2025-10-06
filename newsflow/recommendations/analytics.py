"""
User preference analytics for NewsFlow.

Analyzes user reading patterns and automatically updates preferences
based on interaction history.
"""

import logging
from collections import Counter
from collections import defaultdict
from datetime import timedelta

from django.core.cache import cache
from django.db.models import QuerySet
from django.utils import timezone

from newsflow.news.models import Category
from newsflow.news.models import NewsSource
from newsflow.news.models import UserInteraction
from newsflow.users.models import UserProfile

logger = logging.getLogger(__name__)


class UserPreferenceAnalyzer:
    """
    Analyzes user reading patterns and preferences.

    Provides insights into user behavior and automatically
    updates user profiles based on interaction patterns.
    """

    def __init__(self, cache_timeout: int = 3600):
        """
        Initialize the preference analyzer.

        Args:
            cache_timeout: Cache timeout in seconds (default: 1 hour)
        """
        self.cache_timeout = cache_timeout

    def analyze_reading_patterns(
        self,
        user_id: int,
        days: int = 30,
    ) -> dict:
        """
        Analyze comprehensive reading patterns for a user.

        Args:
            user_id: User ID to analyze
            days: Number of days to analyze

        Returns:
            Dictionary with detailed analytics
        """
        cache_key = f"reading_patterns_{user_id}_{days}"
        cached_result = cache.get(cache_key)

        if cached_result:
            return cached_result

        cutoff_date = timezone.now() - timedelta(days=days)

        # Get all user interactions
        interactions = (
            UserInteraction.objects.filter(
                user_id=user_id,
                created_at__gte=cutoff_date,
            )
            .select_related("article", "article__source")
            .prefetch_related("article__categories")
        )

        if not interactions:
            logger.info(f"No interactions found for user {user_id} in last {days} days")
            return self._empty_analytics()

        analytics = {
            "period_days": days,
            "total_articles_read": 0,
            "total_reading_time": 0,
            "categories": {},
            "sources": {},
            "reading_times": {
                "hourly": defaultdict(int),
                "daily": defaultdict(int),
                "weekly": defaultdict(int),
            },
            "engagement": {
                "likes": 0,
                "shares": 0,
                "comments": 0,
                "bookmarks": 0,
            },
            "topics": [],
            "average_read_time": 0,
            "peak_reading_hour": None,
            "peak_reading_day": None,
            "favorite_category": None,
            "favorite_source": None,
            "reading_velocity": 0,  # Articles per day
            "engagement_rate": 0,  # Percentage of articles engaged with
        }

        # Category statistics
        category_stats = defaultdict(
            lambda: {
                "count": 0,
                "likes": 0,
                "shares": 0,
                "total_time": 0,
                "avg_time": 0,
            },
        )

        # Source statistics
        source_stats = defaultdict(
            lambda: {
                "count": 0,
                "likes": 0,
                "shares": 0,
                "total_time": 0,
                "avg_time": 0,
            },
        )

        # Keyword frequency
        keyword_counter = Counter()

        # Process interactions
        for interaction in interactions:
            article = interaction.article

            # Count by interaction type
            if interaction.action == UserInteraction.ActionType.VIEW:
                analytics["total_articles_read"] += 1

                # Reading time analysis
                if interaction.reading_time:
                    analytics["total_reading_time"] += interaction.reading_time
                    category_stats[article.category.name]["total_time"] += (
                        interaction.reading_time
                    )
                    source_stats[article.source.name]["total_time"] += (
                        interaction.reading_time
                    )

                # Time-based patterns
                hour = interaction.created_at.hour
                day_name = interaction.created_at.strftime("%A")
                week_num = interaction.created_at.isocalendar()[1]

                analytics["reading_times"]["hourly"][hour] += 1
                analytics["reading_times"]["daily"][day_name] += 1
                analytics["reading_times"]["weekly"][week_num] += 1

                # Category and source counts
                categories = article.categories.all()
                for category in categories:
                    category_stats[category.name]["count"] += 1
                source_stats[article.source.name]["count"] += 1

                # Keywords
                if article.keywords:
                    keyword_counter.update(article.keywords)

            elif interaction.action == UserInteraction.ActionType.LIKE:
                analytics["engagement"]["likes"] += 1
                categories = article.categories.all()
                for category in categories:
                    category_stats[category.name]["likes"] += 1
                source_stats[article.source.name]["likes"] += 1

            elif interaction.action == UserInteraction.ActionType.SHARE:
                analytics["engagement"]["shares"] += 1
                categories = article.categories.all()
                for category in categories:
                    category_stats[category.name]["shares"] += 1
                source_stats[article.source.name]["shares"] += 1

            elif interaction.action == UserInteraction.ActionType.COMMENT:
                analytics["engagement"]["comments"] += 1

            elif interaction.action == UserInteraction.ActionType.BOOKMARK:
                analytics["engagement"]["bookmarks"] += 1

        # Calculate aggregates
        if analytics["total_articles_read"] > 0:
            # Average reading time
            analytics["average_read_time"] = (
                analytics["total_reading_time"] / analytics["total_articles_read"]
            )

            # Reading velocity
            analytics["reading_velocity"] = analytics["total_articles_read"] / days

            # Engagement rate
            total_engagements = sum(analytics["engagement"].values())
            analytics["engagement_rate"] = (
                total_engagements / analytics["total_articles_read"] * 100
            )

        # Peak reading times
        if analytics["reading_times"]["hourly"]:
            peak_hour = max(
                analytics["reading_times"]["hourly"].items(),
                key=lambda x: x[1],
            )
            analytics["peak_reading_hour"] = peak_hour[0]

        if analytics["reading_times"]["daily"]:
            peak_day = max(
                analytics["reading_times"]["daily"].items(),
                key=lambda x: x[1],
            )
            analytics["peak_reading_day"] = peak_day[0]

        # Process category statistics
        for category, stats in category_stats.items():
            if stats["count"] > 0:
                stats["avg_time"] = stats["total_time"] / stats["count"]
                stats["engagement_score"] = (
                    stats["count"] + (stats["likes"] * 2) + (stats["shares"] * 3)
                )
            analytics["categories"][category] = stats

        # Process source statistics
        for source, stats in source_stats.items():
            if stats["count"] > 0:
                stats["avg_time"] = stats["total_time"] / stats["count"]
                stats["engagement_score"] = (
                    stats["count"] + (stats["likes"] * 2) + (stats["shares"] * 3)
                )
            analytics["sources"][source] = stats

        # Favorite category and source
        if analytics["categories"]:
            fav_category = max(
                analytics["categories"].items(),
                key=lambda x: x[1]["engagement_score"],
            )
            analytics["favorite_category"] = {
                "name": fav_category[0],
                "stats": fav_category[1],
            }

        if analytics["sources"]:
            fav_source = max(
                analytics["sources"].items(),
                key=lambda x: x[1]["engagement_score"],
            )
            analytics["favorite_source"] = {
                "name": fav_source[0],
                "stats": fav_source[1],
            }

        # Top topics/keywords
        analytics["topics"] = [
            {"keyword": keyword, "frequency": count}
            for keyword, count in keyword_counter.most_common(20)
        ]

        # Reading streak
        analytics["reading_streak"] = self._calculate_reading_streak(user_id)

        # Content preferences
        analytics["content_preferences"] = self._analyze_content_preferences(
            interactions,
        )

        # Cache the result
        cache.set(cache_key, analytics, self.cache_timeout)

        return analytics

    def update_user_preferences(
        self,
        user_id: int,
        days: int = 30,
        min_interactions: int = 10,
    ) -> bool:
        """
        Automatically update user preferences based on reading history.

        Args:
            user_id: User ID to update
            days: Number of days to analyze
            min_interactions: Minimum interactions required for update

        Returns:
            True if preferences were updated
        """
        try:
            user_profile = UserProfile.objects.get(user_id=user_id)
        except UserProfile.DoesNotExist:
            logger.error(f"UserProfile not found for user {user_id}")
            return False

        # Analyze reading patterns
        analytics = self.analyze_reading_patterns(user_id, days)

        if analytics["total_articles_read"] < min_interactions:
            logger.info(
                f"Insufficient data for user {user_id}: "
                f"{analytics['total_articles_read']} articles read",
            )
            return False

        # Update preferred categories
        top_categories = self._get_top_categories(analytics, limit=5)
        if top_categories:
            category_names = [cat["name"] for cat in top_categories]
            categories = Category.objects.filter(name__in=category_names)
            user_profile.preferred_categories.set(categories)
            logger.info(
                f"Updated preferred categories for user {user_id}: {category_names}",
            )

        # Update preferred sources
        top_sources = self._get_top_sources(analytics, limit=5)
        if top_sources:
            source_names = [src["name"] for src in top_sources]
            sources = NewsSource.objects.filter(name__in=source_names)
            user_profile.preferred_sources.set(sources)
            logger.info(f"Updated preferred sources for user {user_id}: {source_names}")

        # Update reading preferences
        user_profile.reading_preferences = {
            "average_read_time": analytics["average_read_time"],
            "peak_reading_hour": analytics["peak_reading_hour"],
            "peak_reading_day": analytics["peak_reading_day"],
            "reading_velocity": analytics["reading_velocity"],
            "engagement_rate": analytics["engagement_rate"],
            "favorite_topics": [t["keyword"] for t in analytics["topics"][:10]],
            "last_updated": timezone.now().isoformat(),
        }

        user_profile.save()

        # Clear cached data
        cache.delete(f"user_profile_vector_{user_id}")
        cache.delete(f"hybrid_feed_{user_id}_*")

        return True

    def get_user_insights(self, user_id: int) -> dict:
        """
        Get actionable insights about user behavior.

        Args:
            user_id: User ID

        Returns:
            Dictionary with user insights
        """
        analytics = self.analyze_reading_patterns(user_id, days=30)

        insights = {
            "reading_level": self._classify_reading_level(analytics),
            "engagement_level": self._classify_engagement_level(analytics),
            "content_diversity": self._calculate_content_diversity(analytics),
            "recommendations": [],
            "achievements": [],
        }

        # Generate recommendations based on patterns
        if analytics["reading_velocity"] < 1:
            insights["recommendations"].append(
                "Try to read at least one article per day to stay informed",
            )

        if analytics["engagement_rate"] < 10:
            insights["recommendations"].append(
                "Engage more with articles you enjoy by liking or sharing them",
            )

        if len(analytics["categories"]) < 3:
            insights["recommendations"].append(
                "Explore more categories to diversify your reading",
            )

        # Check achievements
        if analytics["reading_streak"] >= 7:
            insights["achievements"].append(
                {
                    "title": "Week Streak",
                    "description": f"{analytics['reading_streak']} day reading streak!",
                },
            )

        if analytics["total_articles_read"] >= 100:
            insights["achievements"].append(
                {
                    "title": "Avid Reader",
                    "description": f"Read {analytics['total_articles_read']} articles",
                },
            )

        if analytics["engagement_rate"] >= 50:
            insights["achievements"].append(
                {
                    "title": "Super Engaged",
                    "description": "High engagement rate with content",
                },
            )

        return insights

    def get_category_affinity(self, user_id: int) -> list[tuple[str, float]]:
        """
        Calculate user's affinity score for each category.

        Args:
            user_id: User ID

        Returns:
            List of (category_name, affinity_score) tuples
        """
        analytics = self.analyze_reading_patterns(user_id, days=30)

        affinities = []
        total_engagement = sum(
            cat["engagement_score"] for cat in analytics["categories"].values()
        )

        if total_engagement > 0:
            for category_name, stats in analytics["categories"].items():
                affinity = stats["engagement_score"] / total_engagement
                affinities.append((category_name, affinity))

        affinities.sort(key=lambda x: x[1], reverse=True)
        return affinities

    def _get_top_categories(self, analytics: dict, limit: int = 5) -> list[dict]:
        """Get top categories by engagement score."""
        if not analytics["categories"]:
            return []

        sorted_categories = sorted(
            analytics["categories"].items(),
            key=lambda x: x[1]["engagement_score"],
            reverse=True,
        )

        return [
            {"name": name, "stats": stats} for name, stats in sorted_categories[:limit]
        ]

    def _get_top_sources(self, analytics: dict, limit: int = 5) -> list[dict]:
        """Get top sources by engagement score."""
        if not analytics["sources"]:
            return []

        sorted_sources = sorted(
            analytics["sources"].items(),
            key=lambda x: x[1]["engagement_score"],
            reverse=True,
        )

        return [
            {"name": name, "stats": stats} for name, stats in sorted_sources[:limit]
        ]

    def _calculate_reading_streak(self, user_id: int) -> int:
        """Calculate current reading streak in days."""
        interactions = (
            UserInteraction.objects.filter(
                user_id=user_id,
                action=UserInteraction.ActionType.VIEW,
            )
            .values("created_at__date")
            .distinct()
            .order_by("-created_at__date")
        )

        if not interactions:
            return 0

        streak = 0
        current_date = timezone.now().date()

        for interaction in interactions:
            interaction_date = interaction["created_at__date"]

            if (current_date - interaction_date).days == streak:
                streak += 1
            else:
                break

        return streak

    def _analyze_content_preferences(self, interactions: QuerySet) -> dict:
        """Analyze content type preferences."""
        preferences = {
            "article_length": defaultdict(int),
            "content_type": defaultdict(int),
            "reading_time_distribution": defaultdict(int),
        }

        for interaction in interactions:
            if interaction.action != UserInteraction.ActionType.VIEW:
                continue

            article = interaction.article

            # Article length preference
            word_count = len(article.content.split()) if article.content else 0
            if word_count < 300:
                preferences["article_length"]["short"] += 1
            elif word_count < 800:
                preferences["article_length"]["medium"] += 1
            else:
                preferences["article_length"]["long"] += 1

            # Reading time distribution
            if interaction.reading_time:
                if interaction.reading_time < 60:
                    preferences["reading_time_distribution"]["quick"] += 1
                elif interaction.reading_time < 180:
                    preferences["reading_time_distribution"]["moderate"] += 1
                else:
                    preferences["reading_time_distribution"]["deep"] += 1

        return dict(preferences)

    def _classify_reading_level(self, analytics: dict) -> str:
        """Classify user's reading level."""
        velocity = analytics["reading_velocity"]

        if velocity >= 10:
            return "Power Reader"
        if velocity >= 5:
            return "Avid Reader"
        if velocity >= 2:
            return "Regular Reader"
        if velocity >= 1:
            return "Casual Reader"
        return "Occasional Reader"

    def _classify_engagement_level(self, analytics: dict) -> str:
        """Classify user's engagement level."""
        rate = analytics["engagement_rate"]

        if rate >= 50:
            return "Highly Engaged"
        if rate >= 25:
            return "Engaged"
        if rate >= 10:
            return "Moderately Engaged"
        return "Low Engagement"

    def _calculate_content_diversity(self, analytics: dict) -> float:
        """Calculate content diversity score (0-1)."""
        if not analytics["categories"]:
            return 0.0

        # Calculate Shannon entropy for diversity
        total_reads = sum(cat["count"] for cat in analytics["categories"].values())
        if total_reads == 0:
            return 0.0

        entropy = 0
        for cat in analytics["categories"].values():
            if cat["count"] > 0:
                p = cat["count"] / total_reads
                entropy -= p * (
                    p if p == 0 else p * (1 if p == 1 else p.bit_length() - 1)
                )

        # Normalize to 0-1 range
        max_entropy = (
            len(analytics["categories"]).bit_length() - 1
            if len(analytics["categories"]) > 1
            else 1
        )
        diversity_score = min(1.0, entropy / max_entropy) if max_entropy > 0 else 0.0

        return diversity_score

    def _empty_analytics(self) -> dict:
        """Return empty analytics structure."""
        return {
            "period_days": 0,
            "total_articles_read": 0,
            "total_reading_time": 0,
            "categories": {},
            "sources": {},
            "reading_times": {
                "hourly": {},
                "daily": {},
                "weekly": {},
            },
            "engagement": {
                "likes": 0,
                "shares": 0,
                "comments": 0,
                "bookmarks": 0,
            },
            "topics": [],
            "average_read_time": 0,
            "peak_reading_hour": None,
            "peak_reading_day": None,
            "favorite_category": None,
            "favorite_source": None,
            "reading_velocity": 0,
            "engagement_rate": 0,
            "reading_streak": 0,
            "content_preferences": {},
        }
