"""
User profile model for newsflow.
"""

import uuid

from django.db import models
from django.db.models import CharField
from django.db.models import UUIDField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel


class UserProfile(TimeStampedModel):
    """Extended user profile with NewsFlow-specific preferences."""

    class ThemeChoice(models.TextChoices):
        """Available theme options for user interface."""

        LIGHT = "light", _("Light")
        DARK = "dark", _("Dark")
        SYSTEM = "system", _("System")

    # UUID field for better security and URLs
    uuid = UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    # One-to-one relationship with User
    user = models.OneToOneField(
        "User",
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("User"),
    )

    # Theme preference choices (moved from User model)
    theme_preference = CharField(
        _("Theme Preference"),
        max_length=10,
        choices=ThemeChoice.choices,
        default=ThemeChoice.SYSTEM,
        help_text=_("Choose your preferred theme or follow system setting"),
    )

    # Reading preferences
    reading_speed = models.IntegerField(
        _("Reading Speed (words per minute)"),
        default=200,
        help_text=_("Used to calculate reading time estimates"),
    )

    # Notification preferences (JSON field for flexibility)
    notification_preferences = models.JSONField(
        _("Notification Preferences"),
        default=dict,
        blank=True,
        help_text=_("User notification settings"),
    )

    # Onboarding and preferences
    is_onboarded = models.BooleanField(
        _("Is Onboarded"),
        default=False,
        help_text=_("Whether user has completed the onboarding process"),
    )

    # Proper Django relationships
    preferred_categories = models.ManyToManyField(
        "news.Category",
        related_name="users",
        verbose_name=_("Preferred Categories"),
        blank=True,
        help_text=_("Categories the user is interested in"),
    )

    preferred_sources = models.ManyToManyField(
        "news.NewsSource",
        related_name="users",
        verbose_name=_("Preferred Sources"),
        blank=True,
        help_text=_("News sources the user prefers"),
    )

    class Meta:
        verbose_name = _("User Profile")
        verbose_name_plural = _("User Profiles")
        ordering = ["user__email"]

    def __str__(self):
        return f"{self.user.email} Profile"

    def get_absolute_url(self):
        """Get URL for user profile detail view."""
        return reverse("users:profile-detail", kwargs={"uuid": str(self.uuid)})

    def get_default_notification_preferences(self):
        """Get default notification preferences."""
        return {
            "email_notifications": True,
            "breaking_news": True,
            "daily_digest": True,
            "weekly_summary": False,
            "article_recommendations": True,
            "category_updates": True,
        }

    def save(self, *args, **kwargs):
        # Set default notification preferences if empty
        if not self.notification_preferences:
            self.notification_preferences = self.get_default_notification_preferences()
        super().save(*args, **kwargs)

    def get_recommended_articles_count(self):
        """Get count of articles in user's preferred categories from last 24 hours."""
        from datetime import timedelta

        from django.utils import timezone

        from newsflow.news.models import Article

        if not self.preferred_categories.exists():
            return 0

        yesterday = timezone.now() - timedelta(hours=24)
        return (
            Article.objects.published()
            .filter(
                categories__in=self.preferred_categories.all(),
                published_at__gte=yesterday,
            )
            .distinct()
            .count()
        )

    def get_reading_history_count(self):
        """Get count of articles this user has read."""
        from newsflow.news.models.user_interaction import UserInteraction

        return self.user.interactions.filter(
            action=UserInteraction.ActionType.VIEW,
        ).count()

    def get_bookmarked_articles_count(self):
        """Get count of articles this user has bookmarked."""
        from newsflow.news.models.user_interaction import UserInteraction

        return self.user.interactions.filter(
            action=UserInteraction.ActionType.BOOKMARK,
        ).count()

    def mark_onboarded(self, categories=None, sources=None):
        """Mark user as onboarded and save their preferences."""
        self.is_onboarded = True
        if categories:
            self.preferred_categories.set(categories)
        if sources:
            self.preferred_sources.set(sources)
        self.save(update_fields=["is_onboarded"])

    def needs_onboarding(self):
        """Check if user needs to go through onboarding."""
        return not self.is_onboarded

    def has_preferences(self):
        """Check if user has set any preferences."""
        return self.preferred_categories.exists() or self.preferred_sources.exists()

    def get_preferred_category_codes(self):
        """Get list of preferred category codes."""
        return list(self.preferred_categories.values_list("slug", flat=True))

    def get_preferred_source_ids(self):
        """Get list of preferred source IDs."""
        return list(self.preferred_sources.values_list("id", flat=True))
