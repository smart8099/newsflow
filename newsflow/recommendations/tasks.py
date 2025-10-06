"""
Celery tasks for NewsFlow recommendation system.

Background tasks for updating recommendations, computing similarities,
and maintaining recommendation caches.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.db.models import Count
from django.db.models import Q
from django.utils import timezone

from newsflow.news.models import Article
from newsflow.news.models import UserInteraction
from newsflow.users.models import UserProfile

from .analytics import UserPreferenceAnalyzer
from .engine import ContentBasedRecommender
from .hybrid import HybridRecommender

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    name="recommendations.update_recommendations_cache",
)
def update_recommendations_cache(self, user_id: int):
    """
    Pre-compute and cache recommendations for a specific user.

    This task is triggered after user interactions to ensure
    fresh recommendations are available.

    Args:
        user_id: User ID to update recommendations for
    """
    try:
        logger.info(f"Updating recommendation cache for user {user_id}")

        # Initialize recommender
        hybrid_recommender = HybridRecommender()

        # Generate different types of recommendations
        recommendations = {
            "personalized_feed": hybrid_recommender.get_personalized_feed(
                user_id,
                limit=30,
                use_cache=False,
            ),
            "explore_feed": hybrid_recommender.get_explore_feed(
                user_id,
                limit=20,
            ),
        }

        # Cache recommendations with different keys
        cache_timeout = 3600  # 1 hour

        for rec_type, articles in recommendations.items():
            cache_key = f"cached_{rec_type}_{user_id}"
            cache.set(cache_key, articles, cache_timeout)

        # Also update user profile vector cache
        content_recommender = ContentBasedRecommender()
        content_recommender.get_user_profile_vector(user_id)

        logger.info(
            f"Successfully cached recommendations for user {user_id}: "
            f"{len(recommendations['personalized_feed'])} personalized, "
            f"{len(recommendations['explore_feed'])} explore",
        )

        return {
            "user_id": user_id,
            "personalized_count": len(recommendations["personalized_feed"]),
            "explore_count": len(recommendations["explore_feed"]),
            "status": "success",
        }

    except Exception as e:
        logger.error(f"Error updating recommendations cache for user {user_id}: {e}")
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 300},
    name="recommendations.batch_update_recommendations",
)
def batch_update_recommendations(self):
    """
    Update recommendations for all active users.

    Runs daily to ensure all users have fresh recommendations.
    Active users are those who have interacted in the last 30 days.
    """
    try:
        logger.info("Starting batch update of recommendations")

        # Get active users (interacted in last 30 days)
        cutoff_date = timezone.now() - timedelta(days=30)
        active_user_ids = (
            UserInteraction.objects.filter(
                created_at__gte=cutoff_date,
            )
            .values_list("user_id", flat=True)
            .distinct()
        )

        active_users = list(set(active_user_ids))  # Remove duplicates
        logger.info(f"Found {len(active_users)} active users to update")

        # Process users in batches
        batch_size = 50
        successful_updates = 0
        failed_updates = 0

        for i in range(0, len(active_users), batch_size):
            batch_users = active_users[i : i + batch_size]

            for user_id in batch_users:
                try:
                    # Trigger individual user update task
                    update_recommendations_cache.delay(user_id)
                    successful_updates += 1

                except Exception as e:
                    logger.error(f"Failed to queue update for user {user_id}: {e}")
                    failed_updates += 1

            # Brief pause between batches
            if i + batch_size < len(active_users):
                import time

                time.sleep(1)

        logger.info(
            f"Batch update completed: {successful_updates} queued, "
            f"{failed_updates} failed",
        )

        return {
            "total_users": len(active_users),
            "successful_updates": successful_updates,
            "failed_updates": failed_updates,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Error in batch update recommendations: {e}")
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 600},
    name="recommendations.compute_article_similarities",
)
def compute_article_similarities(self):
    """
    Pre-compute similarity matrix for articles.

    This task runs every 6 hours to update article vectors
    and compute similarities for the recommendation engine.
    """
    try:
        logger.info("Starting article similarity computation")

        # Initialize content recommender
        content_recommender = ContentBasedRecommender()

        # Force rebuild of article vectors
        article_vectors, article_ids = content_recommender._build_article_vectors(
            force_rebuild=True,
        )

        if not article_ids:
            logger.warning("No articles found for similarity computation")
            return {"status": "no_articles", "count": 0}

        # Pre-compute similarities for recent popular articles
        popular_article_ids = (
            Article.objects.filter(
                id__in=article_ids,
            )
            .annotate(
                interaction_count=Count("interactions"),
            )
            .filter(
                interaction_count__gt=5,
            )
            .order_by("-interaction_count")[:500]
            .values_list("id", flat=True)
        )

        similarities_computed = 0

        for article_id in popular_article_ids:
            try:
                # This will compute and cache similarities
                similar_articles = content_recommender.get_similar_articles(
                    article_id,
                    limit=10,
                )
                similarities_computed += 1

                # Cache the result specifically
                cache_key = f"similar_articles_{article_id}"
                cache.set(cache_key, similar_articles, 21600)  # 6 hours

            except Exception as e:
                logger.warning(
                    f"Failed to compute similarities for article {article_id}: {e}",
                )

        logger.info(
            f"Article similarity computation completed: "
            f"{similarities_computed} articles processed",
        )

        return {
            "total_articles": len(article_ids),
            "popular_articles": len(popular_article_ids),
            "similarities_computed": similarities_computed,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Error computing article similarities: {e}")
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    name="recommendations.update_user_preferences",
)
def update_user_preferences(self, user_id: int):
    """
    Update user preferences based on recent reading history.

    Args:
        user_id: User ID to update preferences for
    """
    try:
        logger.info(f"Updating preferences for user {user_id}")

        analyzer = UserPreferenceAnalyzer()
        updated = analyzer.update_user_preferences(user_id, days=30)

        if updated:
            # Clear recommendation caches for this user
            cache_keys = [
                f"hybrid_feed_{user_id}_*",
                f"user_profile_vector_{user_id}",
                f"fresh_content_{user_id}_*",
                f"reading_patterns_{user_id}_*",
            ]

            for key_pattern in cache_keys:
                if "*" in key_pattern:
                    # For wildcard patterns, we'd need to implement cache key deletion
                    # For now, we'll just delete specific known keys
                    for limit in [10, 20, 30]:
                        for exclude in [True, False]:
                            specific_key = key_pattern.replace(
                                "*",
                                f"{limit}_{exclude}",
                            )
                            cache.delete(specific_key)
                else:
                    cache.delete(key_pattern)

            logger.info(f"Successfully updated preferences for user {user_id}")
            return {"user_id": user_id, "updated": True, "status": "success"}
        logger.info(f"No preference update needed for user {user_id}")
        return {"user_id": user_id, "updated": False, "status": "no_update"}

    except Exception as e:
        logger.error(f"Error updating preferences for user {user_id}: {e}")
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 300},
    name="recommendations.batch_update_user_preferences",
)
def batch_update_user_preferences(self):
    """
    Update user preferences for all active users.

    Runs weekly to keep user preferences up to date.
    """
    try:
        logger.info("Starting batch update of user preferences")

        # Get users who have recent interactions but haven't had preferences updated recently
        cutoff_date = timezone.now() - timedelta(days=7)
        recent_cutoff = timezone.now() - timedelta(days=1)

        # Users with recent interactions
        active_users = (
            UserInteraction.objects.filter(
                created_at__gte=cutoff_date,
            )
            .values_list("user_id", flat=True)
            .distinct()
        )

        # Filter to users who might need preference updates
        user_profiles = (
            UserProfile.objects.filter(
                user_id__in=active_users,
            )
            .filter(
                Q(updated_at__lt=recent_cutoff)
                | Q(reading_preferences__isnull=True)
                | Q(reading_preferences={}),
            )
            .values_list("user_id", flat=True)
        )

        users_to_update = list(set(user_profiles))
        logger.info(f"Found {len(users_to_update)} users needing preference updates")

        successful_updates = 0
        failed_updates = 0

        for user_id in users_to_update:
            try:
                update_user_preferences.delay(user_id)
                successful_updates += 1
            except Exception as e:
                logger.error(
                    f"Failed to queue preference update for user {user_id}: {e}",
                )
                failed_updates += 1

        logger.info(
            f"Batch preference update completed: {successful_updates} queued, "
            f"{failed_updates} failed",
        )

        return {
            "total_users": len(users_to_update),
            "successful_updates": successful_updates,
            "failed_updates": failed_updates,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Error in batch preference update: {e}")
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 120},
    name="recommendations.clean_recommendation_cache",
)
def clean_recommendation_cache(self):
    """
    Clean up old recommendation cache entries.

    Removes stale cache entries to free up memory.
    """
    try:
        logger.info("Starting recommendation cache cleanup")

        # This is a simplified cleanup - in a real system, you'd want
        # more sophisticated cache management
        cache_patterns = [
            "recommendation_article_vectors",
            "trending_category_*",
            "trending_global_*",
            "breaking_news_*",
            "explore_feed_*",
        ]

        cleaned_count = 0

        # For demonstration, we'll just clear some general caches
        general_keys = [
            "recommendation_article_vectors",
        ]

        for key in general_keys:
            if cache.delete(key):
                cleaned_count += 1

        logger.info(f"Cache cleanup completed: {cleaned_count} entries cleaned")

        return {
            "cleaned_count": cleaned_count,
            "status": "completed",
        }

    except Exception as e:
        logger.error(f"Error cleaning recommendation cache: {e}")
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    name="recommendations.trigger_user_recommendation_update",
)
def trigger_user_recommendation_update(self, user_id: int, interaction_type: str):
    """
    Trigger recommendation update after user interaction.

    This is called after significant user interactions to keep
    recommendations fresh.

    Args:
        user_id: User ID that interacted
        interaction_type: Type of interaction (view, like, share, etc.)
    """
    try:
        # Only trigger updates for certain interaction types
        from newsflow.news.models import UserInteraction

        significant_interactions = [
            UserInteraction.ActionType.VIEW,
            UserInteraction.ActionType.LIKE,
            UserInteraction.ActionType.SHARE,
            UserInteraction.ActionType.BOOKMARK,
        ]

        if interaction_type not in significant_interactions:
            return {"status": "skipped", "reason": "interaction_not_significant"}

        # Check if we've already updated recently for this user
        cache_key = f"last_rec_update_{user_id}"
        last_update = cache.get(cache_key)

        if last_update:
            # Don't update more than once every 10 minutes
            return {"status": "skipped", "reason": "recent_update"}

        # Mark that we're updating
        cache.set(cache_key, timezone.now(), 600)  # 10 minutes

        # Queue the update
        update_recommendations_cache.delay(user_id)

        # If it's a significant engagement, also queue preference update
        if interaction_type in ["like", "share", "bookmark"]:
            update_user_preferences.delay(user_id)

        logger.info(
            f"Triggered recommendation update for user {user_id} after {interaction_type}",
        )

        return {
            "user_id": user_id,
            "interaction_type": interaction_type,
            "status": "triggered",
        }

    except Exception as e:
        logger.error(
            f"Error triggering recommendation update for user {user_id}: {e}",
        )
        raise


# Periodic task schedule (to be added to Django settings)
RECOMMENDATION_TASK_SCHEDULE = {
    "batch-update-recommendations": {
        "task": "recommendations.batch_update_recommendations",
        "schedule": 24 * 60 * 60,  # Daily
    },
    "compute-article-similarities": {
        "task": "recommendations.compute_article_similarities",
        "schedule": 6 * 60 * 60,  # Every 6 hours
    },
    "batch-update-user-preferences": {
        "task": "recommendations.batch_update_user_preferences",
        "schedule": 7 * 24 * 60 * 60,  # Weekly
    },
    "clean-recommendation-cache": {
        "task": "recommendations.clean_recommendation_cache",
        "schedule": 12 * 60 * 60,  # Every 12 hours
    },
}
