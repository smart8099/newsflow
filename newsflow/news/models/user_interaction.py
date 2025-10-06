"""
UserInteraction model and manager for news app.
"""

import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

User = get_user_model()


class UserInteractionManager(models.Manager):
    """Custom manager for UserInteraction."""

    def by_user(self, user):
        """Filter interactions by user."""
        return self.filter(user=user)

    def by_action(self, action):
        """Filter interactions by action type."""
        return self.filter(action=action)

    def by_article(self, article):
        """Filter interactions by article."""
        return self.filter(article=article)

    def recent(self, limit=10):
        """Get recent interactions."""
        return self.order_by("-created")[:limit]


class UserInteraction(TimeStampedModel):
    """Model representing user interactions with articles."""

    class ActionType(models.TextChoices):
        """Available interaction types."""

        VIEW = "view", _("View")
        LIKE = "like", _("Like")
        SHARE = "share", _("Share")
        BOOKMARK = "bookmark", _("Bookmark")
        COMMENT = "comment", _("Comment")
        CLICK = "click", _("Click")

    # UUID field for better security and URLs
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="interactions",
        verbose_name=_("User"),
    )
    article = models.ForeignKey(
        "Article",  # Use string reference to avoid circular imports
        on_delete=models.CASCADE,
        related_name="interactions",
        verbose_name=_("Article"),
    )

    action = models.CharField(
        _("Action"),
        max_length=20,
        choices=ActionType.choices,
    )

    # Optional metadata
    metadata = models.JSONField(
        _("Metadata"),
        default=dict,
        blank=True,
        help_text=_("Additional data about the interaction"),
    )

    # Tracking fields
    ip_address = models.GenericIPAddressField(_("IP Address"), null=True, blank=True)
    user_agent = models.TextField(_("User Agent"), blank=True)
    reading_time = models.IntegerField(
        _("Reading Time (seconds)"),
        null=True,
        blank=True,
        help_text=_("Time spent reading the article"),
    )

    objects = UserInteractionManager()

    class Meta:
        verbose_name = _("User Interaction")
        verbose_name_plural = _("User Interactions")
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["article"]),
            models.Index(fields=["action"]),
            models.Index(fields=["created"]),
            models.Index(fields=["user", "article"]),
            models.Index(fields=["user", "action"]),
        ]

    def __str__(self):
        return f"{self.user.email} {self.action} {self.article.title[:50]}"

    def get_absolute_url(self):
        """Get URL for interaction detail view."""
        return reverse("news:interaction-detail", kwargs={"uuid": str(self.uuid)})

    @property
    def reading_time_minutes(self):
        """Get reading time in minutes."""
        if self.reading_time:
            return round(self.reading_time / 60, 1)
        return None

    @classmethod
    def record_interaction(cls, user, article, action, **kwargs):
        """
        Helper method to record a user interaction.
        Now allows multiple interactions of any type for better recommendation data.
        """
        # Always create new interaction for better recommendation tracking
        return cls.objects.create(
            user=user,
            article=article,
            action=action,
            **kwargs,
        ), True

    @classmethod
    def get_latest_interaction(cls, user, article, action):
        """Get the most recent interaction of a specific type."""
        return cls.objects.filter(
            user=user,
            article=article,
            action=action,
        ).first()

    @classmethod
    def has_interaction(cls, user, article, action):
        """Check if user has performed a specific action on an article."""
        return cls.objects.filter(
            user=user,
            article=article,
            action=action,
        ).exists()

    @classmethod
    def get_user_actions_on_article(cls, user, article):
        """Get all unique actions a user has performed on an article."""
        return (
            cls.objects.filter(
                user=user,
                article=article,
            )
            .values_list("action", flat=True)
            .distinct()
        )
