"""
BookmarkedArticle, LikedArticle and ReadArticle models for news app.
"""

from django.contrib.auth import get_user_model
from django.db import models
from model_utils.models import TimeStampedModel

User = get_user_model()


class BookmarkedArticle(TimeStampedModel):
    """Model representing bookmarked articles by users."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="bookmarks",
    )
    article = models.ForeignKey(
        "Article",  # Use string reference to avoid circular imports
        on_delete=models.CASCADE,
        related_name="bookmarked_by",
    )

    # Optional notes
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ["user", "article"]
        ordering = ["-created"]

    def __str__(self):
        return f"{self.user.email} bookmarked {self.article.title}"


class LikedArticle(TimeStampedModel):
    """Model representing liked articles by users."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="liked_articles",
    )
    article = models.ForeignKey(
        "Article",  # Use string reference to avoid circular imports
        on_delete=models.CASCADE,
        related_name="liked_by",
    )

    class Meta:
        unique_together = ["user", "article"]
        ordering = ["-created"]

    def __str__(self):
        return f"{self.user.email} liked {self.article.title}"


class ReadArticle(TimeStampedModel):
    """Model representing articles read by users."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="read_articles",
    )
    article = models.ForeignKey(
        "Article",  # Use string reference to avoid circular imports
        on_delete=models.CASCADE,
        related_name="read_by",
    )

    class Meta:
        unique_together = ["user", "article"]
        ordering = ["-created"]

    def __str__(self):
        return f"{self.user.email} read {self.article.title}"
