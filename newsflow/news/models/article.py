"""
Article model and manager for news app.
"""

import uuid
from datetime import timedelta

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchQuery
from django.contrib.postgres.search import SearchRank
from django.contrib.postgres.search import SearchVector
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel


class ArticleManager(models.Manager):
    """Custom manager for Article."""

    def published(self):
        """Return only published articles."""
        return self.filter(is_published=True)

    def featured(self):
        """Return only featured articles."""
        return self.filter(is_featured=True, is_published=True)

    def trending(self, hours=24):
        """Return trending articles based on view count in the last N hours."""
        since = timezone.now() - timedelta(hours=hours)
        return (
            self.published()
            .filter(
                scraped_at__gte=since,
            )
            .order_by("-view_count")
        )

    def by_category(self, category):
        """Filter articles by category."""
        return self.published().filter(categories=category)

    def recent(self, limit=10):
        """Get recent published articles."""
        return self.published().order_by("-published_at")[:limit]

    def by_source(self, source):
        """Filter articles by news source."""
        return self.published().filter(source=source)

    def with_sentiment(self, sentiment_label):
        """Filter articles by sentiment."""
        return self.published().filter(sentiment_label=sentiment_label)

    def search(self, query, rank_threshold=0.1):
        """
        Full-text search across articles with weighted ranking.
        Args:
            query: Search query string
            rank_threshold: Minimum rank threshold for results
        Returns:
            QuerySet with search results ordered by relevance
        """
        if not query:
            return self.none()

        search_query = SearchQuery(query)

        # Use a combination of pre-built search vectors and on-the-fly vectors for better results
        search_vector = (
            SearchVector("title", weight="A")
            + SearchVector("content", weight="B")
            + SearchVector("summary", weight="B")
            + SearchVector("keywords", weight="C")
        )

        # Add exact title match boost
        from django.db.models import Case
        from django.db.models import FloatField
        from django.db.models import When

        return (
            self.published()
            .annotate(
                rank=SearchRank(search_vector, search_query),
                # Boost exact title matches
                title_boost=Case(
                    When(title__iexact=query, then=2.0),
                    When(title__icontains=query, then=1.5),
                    default=1.0,
                    output_field=FloatField(),
                ),
                final_rank=models.F("rank") * models.F("title_boost"),
            )
            .filter(
                rank__gte=rank_threshold,
            )
            .order_by("-final_rank", "-published_at")
        )

    def advanced_search(self, query, search_type="phrase"):
        """
        Advanced search with different search types.
        Args:
            query: Search query
            search_type: 'phrase', 'plain', or 'web' search
        Returns:
            QuerySet with search results
        """
        if not query:
            return self.none()

        if search_type == "phrase":
            search_query = SearchQuery(query, search_type="phrase")
            rank_threshold = 0.1  # Higher threshold for phrase search
        elif search_type == "web":
            search_query = SearchQuery(query, search_type="websearch")
            rank_threshold = 0.08  # Medium threshold for web search
        else:
            search_query = SearchQuery(query, search_type="plain")
            rank_threshold = 0.05  # Lower threshold for plain search

        # Use the same search vector as the regular search for consistency
        search_vector = (
            SearchVector("title", weight="A")
            + SearchVector("content", weight="B")
            + SearchVector("summary", weight="B")
            + SearchVector("keywords", weight="C")
        )

        # Add exact title match boost
        from django.db.models import Case
        from django.db.models import FloatField
        from django.db.models import When

        return (
            self.published()
            .annotate(
                rank=SearchRank(search_vector, search_query),
                # Boost exact title matches
                title_boost=Case(
                    When(title__iexact=query, then=2.0),
                    When(title__icontains=query, then=1.5),
                    default=1.0,
                    output_field=FloatField(),
                ),
                final_rank=models.F("rank") * models.F("title_boost"),
            )
            .filter(
                rank__gte=rank_threshold,
            )
            .order_by("-final_rank", "-published_at")
        )

    def autocomplete_search(self, query, limit=10):
        """
        Autocomplete search for search suggestions.
        Args:
            query: Partial search query
            limit: Maximum number of suggestions
        Returns:
            QuerySet with title matches
        """
        if not query or len(query) < 2:
            return self.none()

        return (
            self.published()
            .filter(
                title__icontains=query,
            )
            .values("title")
            .distinct()[:limit]
        )

    def build_search_vector(self):
        """
        Build search vector for all articles that don't have one.
        Returns:
            Number of articles updated
        """
        articles_to_update = self.filter(search_vector__isnull=True)
        updated_count = 0

        for article in articles_to_update:
            # Build weighted search vector
            search_vector = (
                SearchVector("title", weight="A")
                + SearchVector("content", weight="B")
                + SearchVector("keywords", weight="C")
            )

            # Update the article
            article.search_vector = search_vector
            article.save(update_fields=["search_vector"])
            updated_count += 1

            # Log progress for large updates
            if updated_count % 100 == 0:
                print(f"Updated search vector for {updated_count} articles...")

        return updated_count


class Article(TimeStampedModel):
    """Model representing a news article."""

    class SentimentType(models.TextChoices):
        """Available sentiment types for articles."""

        POSITIVE = "positive", _("Positive")
        NEUTRAL = "neutral", _("Neutral")
        NEGATIVE = "negative", _("Negative")

    # UUID field for better security and URLs
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    # Basic article information
    title = models.CharField(_("Title"), max_length=500)
    url = models.URLField(_("Article URL"), unique=True)
    content = models.TextField(_("Content"))
    summary = models.TextField(_("Summary"), blank=True)
    author = models.CharField(_("Author"), max_length=200, blank=True)

    # Relationships
    source = models.ForeignKey(
        "NewsSource",  # Use string reference to avoid circular imports
        on_delete=models.CASCADE,
        related_name="articles",
        verbose_name=_("News Source"),
    )
    categories = models.ManyToManyField(
        "Category",  # Use string reference to avoid circular imports
        related_name="articles",
        verbose_name=_("Categories"),
        blank=True,
    )

    # Timestamps
    published_at = models.DateTimeField(_("Published At"))
    scraped_at = models.DateTimeField(_("Scraped At"), auto_now_add=True)

    # Media
    top_image = models.URLField(_("Top Image"), blank=True)

    # Sentiment analysis
    sentiment_score = models.FloatField(
        _("Sentiment Score"),
        null=True,
        blank=True,
        help_text=_("Score from -1 (negative) to 1 (positive)"),
    )

    sentiment_label = models.CharField(
        _("Sentiment Label"),
        max_length=10,
        choices=SentimentType.choices,
        blank=True,
    )

    # Reading metrics
    read_time = models.IntegerField(
        _("Estimated Read Time (minutes)"),
        default=1,
        help_text=_("Estimated reading time in minutes"),
    )
    view_count = models.IntegerField(_("View Count"), default=0)

    # Content metadata
    keywords = models.JSONField(
        _("Keywords"),
        default=list,
        blank=True,
        help_text=_("List of extracted keywords"),
    )

    # Status flags
    is_featured = models.BooleanField(_("Is Featured"), default=False)
    is_published = models.BooleanField(_("Is Published"), default=True)

    # Search vector for full-text search
    search_vector = SearchVectorField(null=True, blank=True)

    objects = ArticleManager()

    class Meta:
        verbose_name = _("Article")
        verbose_name_plural = _("Articles")
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["is_published"]),
            models.Index(fields=["is_featured"]),
            models.Index(fields=["published_at"]),
            models.Index(fields=["scraped_at"]),
            models.Index(fields=["view_count"]),
            models.Index(fields=["sentiment_label"]),
            models.Index(fields=["source"]),
            models.Index(fields=["sentiment_score"]),
            GinIndex(fields=["search_vector"]),
        ]

    def __str__(self):
        return self.title[:100]

    def save(self, *args, **kwargs):
        # Calculate read time if not set
        if not self.read_time and self.content:
            words = len(self.content.split())
            self.read_time = max(1, words // 200)  # Assume 200 words per minute

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Get URL for article detail view."""
        return reverse("news:article-detail", kwargs={"uuid": str(self.uuid)})

    def get_snippet(self, query=None, max_length=200):
        """
        Get a snippet of the article content for search results.
        Args:
            query: Search query to highlight
            max_length: Maximum snippet length
        Returns:
            Text snippet with query highlighted
        """
        if not query:
            return (
                self.summary[:max_length] if self.summary else self.content[:max_length]
            )

        # Simple highlighting - in production you might want to use PostgreSQL's ts_headline
        query_lower = query.lower()
        content = self.content or ""

        # Find the best match position
        query_pos = content.lower().find(query_lower)

        if query_pos == -1:
            # Query not found in content, return beginning
            snippet = content[:max_length]
        else:
            # Extract snippet around the query
            start = max(0, query_pos - max_length // 3)
            end = min(len(content), start + max_length)
            snippet = content[start:end]

            # Highlight the query term (simple replacement)
            snippet = snippet.replace(
                query,
                f"<mark>{query}</mark>",
                1,  # Only highlight first occurrence
            )

        # Add ellipsis if content was truncated
        if len(snippet) >= max_length:
            snippet += "..."

        return snippet

    def update_search_vector(self):
        """Update the search vector for this article."""
        keywords_text = " ".join(self.keywords) if self.keywords else ""

        self.search_vector = (
            SearchVector("title", weight="A")
            + SearchVector("content", weight="B")
            + SearchVector(models.Value(keywords_text), weight="C")
        )
        self.save(update_fields=["search_vector"])

    def increment_view_count(self):
        """Increment the view count for this article."""
        self.view_count += 1
        self.save(update_fields=["view_count"])

    @property
    def is_recent(self):
        """Check if article was published in the last 24 hours."""
        return self.published_at >= timezone.now() - timedelta(hours=24)

    @property
    def is_trending(self):
        """Simple trending check based on views vs age."""
        hours_since_published = (
            timezone.now() - self.published_at
        ).total_seconds() / 3600
        if hours_since_published < 1:
            return self.view_count > 5
        if hours_since_published < 24:
            return self.view_count > 20
        return self.view_count > 50

    def get_category_names(self):
        """Get comma-separated list of category names."""
        return ", ".join([cat.name for cat in self.categories.all()])

    def get_engagement_score(self):
        """
        Calculate weighted engagement score for recommendation ranking.
        Score = views + (likes * 2) + (shares * 3) + (bookmarks * 2)
        """
        # Basic score from views
        score = self.view_count

        # Add interaction-based scoring
        if hasattr(self, "interactions"):
            from .user_interaction import UserInteraction

            interactions = self.interactions.all()
            for interaction in interactions:
                if interaction.action == UserInteraction.ActionType.LIKE:
                    score += 2
                elif interaction.action == UserInteraction.ActionType.SHARE:
                    score += 3
                elif interaction.action == UserInteraction.ActionType.BOOKMARK:
                    score += 2

        return score

    def is_bookmarked_by(self, user):
        """Check if this article is bookmarked by the given user."""
        if not user or not user.is_authenticated:
            return False

        from .bookmarks import BookmarkedArticle

        return BookmarkedArticle.objects.filter(
            user=user,
            article=self,
        ).exists()

    def is_liked_by(self, user):
        """Check if this article is liked by the given user."""
        if not user or not user.is_authenticated:
            return False

        from .bookmarks import LikedArticle

        return LikedArticle.objects.filter(
            user=user,
            article=self,
        ).exists()

    def needs_sentiment_analysis(self):
        """Check if this article needs sentiment analysis."""
        return not self.sentiment_label or self.sentiment_label == ""
