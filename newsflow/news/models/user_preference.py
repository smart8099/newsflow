"""
UserPreference model for news app.
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

User = get_user_model()


class UserPreference(TimeStampedModel):
    """Model representing user preferences for news content."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="news_preferences",
    )

    preferred_categories = models.ManyToManyField(
        "Category",  # Use string reference to avoid circular imports
        blank=True,
    )
    preferred_sources = models.ManyToManyField(
        "NewsSource",  # Use string reference to avoid circular imports
        blank=True,
    )

    email_notifications = models.BooleanField(default=True)
    notification_frequency = models.CharField(
        max_length=20,
        choices=[
            ("instant", "Instant"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("never", "Never"),
        ],
        default="daily",
    )

    class Meta:
        verbose_name = _("User Preference")
        verbose_name_plural = _("User Preferences")

    def __str__(self):
        return f"{self.user.email} preferences"
