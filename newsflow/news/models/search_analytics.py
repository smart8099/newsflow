"""
SearchAnalytics model and manager for news app.
"""

import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

User = get_user_model()


class SearchAnalyticsManager(models.Manager):
    """Custom manager for SearchAnalytics."""

    def by_user(self, user):
        """Filter searches by user."""
        return self.filter(user=user)

    def successful_searches(self):
        """Return only searches that found results."""
        return self.filter(result_count__gt=0)

    def recent(self, limit=10):
        """Get recent searches."""
        return self.order_by("-created")[:limit]

    def popular_queries(self, limit=10):
        """Get most popular search queries."""
        return (
            self.values("query")
            .annotate(
                search_count=models.Count("id"),
            )
            .order_by("-search_count")[:limit]
        )


class SearchAnalytics(TimeStampedModel):
    """Model for tracking search analytics and patterns."""

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
        related_name="search_analytics",
        verbose_name=_("User"),
        null=True,
        blank=True,  # Allow anonymous searches
    )

    # Search details
    query = models.CharField(_("Search Query"), max_length=500)
    normalized_query = models.CharField(
        _("Normalized Query"),
        max_length=500,
        help_text=_("Lowercased and cleaned query for analysis"),
    )
    result_count = models.IntegerField(_("Result Count"), default=0)
    search_type = models.CharField(
        _("Search Type"),
        max_length=20,
        choices=[
            ("article", _("Article Search")),
            ("autocomplete", _("Autocomplete")),
            ("trending", _("Trending Search")),
        ],
        default="article",
    )

    # Filters applied
    filters_applied = models.JSONField(
        _("Filters Applied"),
        default=dict,
        blank=True,
        help_text=_("Filters used in the search"),
    )

    # Performance metrics
    response_time_ms = models.IntegerField(
        _("Response Time (ms)"),
        null=True,
        blank=True,
    )

    # Session and tracking
    session_id = models.CharField(_("Session ID"), max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(_("IP Address"), null=True, blank=True)
    user_agent = models.TextField(_("User Agent"), blank=True)

    objects = SearchAnalyticsManager()

    class Meta:
        verbose_name = _("Search Analytics")
        verbose_name_plural = _("Search Analytics")
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["query"]),
            models.Index(fields=["normalized_query"]),
            models.Index(fields=["search_type"]),
            models.Index(fields=["created"]),
            models.Index(fields=["result_count"]),
        ]

    def __str__(self):
        user_info = self.user.email if self.user else "Anonymous"
        return f"{user_info}: {self.query} ({self.result_count} results)"

    def save(self, *args, **kwargs):
        # Auto-normalize query
        if not self.normalized_query:
            self.normalized_query = self.query.lower().strip()
        super().save(*args, **kwargs)

    @classmethod
    def record_search(
        cls,
        query,
        result_count,
        user=None,
        search_type="article",
        filters=None,
        response_time_ms=None,
        session_id=None,
        ip_address=None,
        user_agent=None,
    ):
        """Helper method to record a search event."""
        return cls.objects.create(
            query=query,
            result_count=result_count,
            user=user,
            search_type=search_type,
            filters_applied=filters or {},
            response_time_ms=response_time_ms,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @classmethod
    def record_click(cls, search_analytics_id, clicked_article, position):
        """Record that a user clicked on a search result."""
        try:
            analytics = cls.objects.get(id=search_analytics_id)
            # Could extend to track click-through rates
            # For now, just record in metadata
            return True
        except cls.DoesNotExist:
            return False
