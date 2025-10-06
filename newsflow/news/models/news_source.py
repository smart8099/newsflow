"""
NewsSource model and manager for news app.
"""

import uuid
from datetime import timedelta

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from .category import CategoryChoices


class NewsSourceManager(models.Manager):
    """Custom manager for NewsSource."""

    def active(self):
        """Return only active news sources."""
        return self.filter(is_active=True)

    def by_type(self, source_type):
        """Filter by source type."""
        return self.filter(source_type=source_type)

    def by_category(self, category):
        """Filter by primary category."""
        return self.filter(primary_category=category)

    def needs_scraping(self):
        """Return sources that need scraping based on frequency."""
        now = timezone.now()
        sources = []
        for source in self.active():
            if source.last_scraped is None:
                sources.append(source)
            else:
                time_since_last_scrape = now - source.last_scraped
                scrape_interval = timedelta(minutes=source.scrape_frequency)
                if time_since_last_scrape >= scrape_interval:
                    sources.append(source)
        return sources


class NewsSource(TimeStampedModel):
    """Model representing a news source for scraping."""

    class SourceType(models.TextChoices):
        """Available source types for news scraping."""

        RSS = "rss", _("RSS Feed")
        WEBSITE = "website", _("Website Scraping")
        API = "api", _("API Integration")

    class BiasRating(models.TextChoices):
        """Political bias ratings for news sources."""

        LEFT = "left", _("Left")
        CENTER = "center", _("Center")
        RIGHT = "right", _("Right")

    # UUID field for better security and URLs
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    # Basic information
    name = models.CharField(_("Source Name"), max_length=100, unique=True)
    slug = models.SlugField(_("Slug"), unique=True, blank=True)
    description = models.TextField(_("Description"), blank=True)

    # URLs and endpoints
    base_url = models.URLField(_("Base URL"), help_text=_("Main website URL"))
    rss_feed = models.URLField(_("RSS Feed URL"), blank=True)
    api_endpoint = models.URLField(_("API Endpoint"), blank=True)

    # Source configuration
    source_type = models.CharField(
        _("Source Type"),
        max_length=10,
        choices=SourceType.choices,
        default=SourceType.RSS,
    )

    primary_category = models.CharField(
        _("Primary Category"),
        max_length=20,
        choices=CategoryChoices.choices,
        default=CategoryChoices.TECHNOLOGY,
    )

    # Localization
    country = models.CharField(
        _("Country Code"),
        max_length=2,
        help_text=_("2-letter ISO country code"),
    )
    language = models.CharField(_("Language"), max_length=10, default="en")

    # Status and configuration
    is_active = models.BooleanField(_("Is Active"), default=True)
    scrape_frequency = models.IntegerField(
        _("Scrape Frequency (minutes)"),
        default=60,
        help_text=_("How often to scrape this source in minutes"),
    )
    max_articles_per_scrape = models.IntegerField(
        _("Max Articles per Scrape"),
        default=50,
    )

    # Performance tracking
    last_scraped = models.DateTimeField(_("Last Scraped"), null=True, blank=True)
    total_articles_scraped = models.IntegerField(_("Total Articles Scraped"), default=0)
    success_rate = models.FloatField(
        _("Success Rate"),
        default=100.0,
        help_text=_("Percentage of successful scraping attempts"),
    )
    average_response_time = models.FloatField(
        _("Average Response Time (seconds)"),
        null=True,
        blank=True,
    )

    # Quality metrics
    credibility_score = models.FloatField(
        _("Credibility Score"),
        default=5.0,
        help_text=_("Rating from 1-10 based on source reliability"),
    )
    bias_rating = models.CharField(
        _("Political Bias"),
        max_length=10,
        choices=BiasRating.choices,
        default=BiasRating.CENTER,
    )

    # Scraping configuration
    custom_selectors = models.JSONField(
        _("Custom CSS Selectors"),
        default=dict,
        blank=True,
        help_text=_("Custom CSS selectors for website scraping"),
    )
    headers = models.JSONField(
        _("HTTP Headers"),
        default=dict,
        blank=True,
        help_text=_("Custom headers for scraping requests"),
    )

    objects = NewsSourceManager()

    class Meta:
        verbose_name = _("News Source")
        verbose_name_plural = _("News Sources")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["source_type"]),
            models.Index(fields=["primary_category"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["last_scraped"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Get URL for news source detail view."""
        return reverse("news:source-detail", kwargs={"uuid": str(self.uuid)})

    def get_articles_count_last_24h(self):
        """Get count of articles scraped in the last 24 hours."""
        if not hasattr(self, "_articles_manager"):
            # Will be available after Article model is created
            return 0
        yesterday = timezone.now() - timedelta(hours=24)
        return self.articles.filter(scraped_at__gte=yesterday).count()

    def update_success_rate(self, successful_attempts, total_attempts):
        """Update the success rate based on scraping attempts."""
        if total_attempts > 0:
            self.success_rate = (successful_attempts / total_attempts) * 100
            self.save(update_fields=["success_rate"])

    def mark_scraped(self, articles_count=0):
        """Mark this source as scraped and update statistics."""
        self.last_scraped = timezone.now()
        self.total_articles_scraped += articles_count
        self.save(update_fields=["last_scraped", "total_articles_scraped"])

    @property
    def next_scrape_time(self):
        """Calculate when this source should next be scraped."""
        if self.last_scraped is None:
            # Never scraped, so it's overdue - return a past time
            return timezone.now() - timedelta(minutes=1)
        return self.last_scraped + timedelta(minutes=self.scrape_frequency)

    @property
    def is_due_for_scraping(self):
        """Check if this source is due for scraping."""
        return timezone.now() >= self.next_scrape_time
