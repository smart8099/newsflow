"""
Category model and manager for news app.
"""

import uuid

from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel


class CategoryChoices(models.TextChoices):
    """News category choices using Django's TextChoices."""

    TECHNOLOGY = "technology", _("Technology")
    BUSINESS = "business", _("Business")
    POLITICS = "politics", _("Politics")
    SPORTS = "sports", _("Sports")
    ENTERTAINMENT = "entertainment", _("Entertainment")
    HEALTH = "health", _("Health")
    SCIENCE = "science", _("Science")
    WORLD = "world", _("World")


class CategoryManager(models.Manager):
    """Custom manager for Category."""

    def active(self):
        """Return only active categories."""
        return self.filter(is_active=True)


class Category(TimeStampedModel):
    """Model representing article categories."""

    # UUID field for better security and URLs
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    name = models.CharField(_("Category Name"), max_length=50)
    slug = models.SlugField(_("Slug"), unique=True, blank=True)
    description = models.TextField(_("Description"), blank=True)
    icon = models.CharField(
        _("Icon"),
        max_length=50,
        blank=True,
        help_text=_("FontAwesome icon class name"),
    )
    is_active = models.BooleanField(_("Is Active"), default=True)

    objects = CategoryManager()

    class Meta:
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Get URL for category detail view."""
        return reverse("news:category-detail", kwargs={"uuid": str(self.uuid)})

    def get_articles_count(self):
        """Get total count of articles in this category."""
        return self.articles.filter(is_published=True).count()

    def get_recent_articles(self, limit=10):
        """Get recent articles in this category."""
        return self.articles.filter(
            is_published=True,
        ).order_by("-published_at")[:limit]
