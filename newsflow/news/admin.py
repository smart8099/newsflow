"""
Django admin configuration for NewsFlow news app.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Article
from .models import BookmarkedArticle
from .models import Category
from .models import LikedArticle
from .models import SearchAnalytics
from .models import UserInteraction
from .models import UserPreference

# Note: NewsSource is registered in the scrapers app with enhanced functionality


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Admin configuration for Article model."""

    list_display = (
        "title_truncated",
        "source",
        "primary_category",
        "published_at",
        "view_count",
        "sentiment_display",
        "is_published",
        "is_featured",
    )
    list_filter = (
        "is_published",
        "is_featured",
        "sentiment_label",
        "source__primary_category",
        "published_at",
        "source",
    )
    search_fields = ("title", "content", "author", "source__name")
    list_editable = ("is_published", "is_featured")
    date_hierarchy = "published_at"
    ordering = ("-published_at",)
    readonly_fields = (
        "uuid",
        "view_count",
        "sentiment_score",
        "sentiment_label",
        "read_time",
        "created",
        "modified",
    )

    fieldsets = (
        (
            _("Content"),
            {
                "fields": ("title", "content", "summary", "author", "url"),
            },
        ),
        (
            _("Media"),
            {
                "fields": ("top_image",),
            },
        ),
        (
            _("Source & Classification"),
            {
                "fields": ("source", "keywords", "categories"),
            },
        ),
        (
            _("Publishing"),
            {
                "fields": ("is_published", "is_featured", "published_at"),
            },
        ),
        (
            _("Analytics"),
            {
                "fields": (
                    "view_count",
                    "sentiment_score",
                    "sentiment_label",
                    "read_time",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("System"),
            {
                "fields": ("uuid", "created", "modified"),
                "classes": ("collapse",),
            },
        ),
    )

    filter_horizontal = ("categories",)

    def title_truncated(self, obj):
        """Truncated title for list display."""
        return obj.title[:60] + "..." if len(obj.title) > 60 else obj.title

    title_truncated.short_description = _("Title")

    def sentiment_display(self, obj):
        """Colored sentiment display."""
        if obj.sentiment_label:
            colors = {
                "positive": "green",
                "negative": "red",
                "neutral": "gray",
            }
            color = colors.get(obj.sentiment_label, "black")
            return format_html(
                '<span style="color: {};">{}</span>',
                color,
                obj.sentiment_label.title(),
            )
        return "-"

    sentiment_display.short_description = _("Sentiment")

    def primary_category(self, obj):
        """Primary category from source."""
        return obj.source.get_primary_category_display() if obj.source else "-"

    primary_category.short_description = _("Category")

    actions = ["make_published", "make_unpublished", "make_featured", "make_unfeatured"]

    def make_published(self, request, queryset):
        """Bulk publish articles."""
        updated = queryset.update(is_published=True)
        self.message_user(request, f"{updated} articles were published.")

    make_published.short_description = _("Publish selected articles")

    def make_unpublished(self, request, queryset):
        """Bulk unpublish articles."""
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} articles were unpublished.")

    make_unpublished.short_description = _("Unpublish selected articles")

    def make_featured(self, request, queryset):
        """Bulk feature articles."""
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"{updated} articles were featured.")

    make_featured.short_description = _("Feature selected articles")

    def make_unfeatured(self, request, queryset):
        """Bulk unfeature articles."""
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"{updated} articles were unfeatured.")

    make_unfeatured.short_description = _("Unfeature selected articles")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin configuration for Category model."""

    list_display = ("name", "slug", "articles_count", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    list_editable = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("uuid", "articles_count")

    def articles_count(self, obj):
        """Number of articles in category."""
        return obj.articles.filter(is_published=True).count()

    articles_count.short_description = _("Articles")


@admin.register(UserInteraction)
class UserInteractionAdmin(admin.ModelAdmin):
    """Admin configuration for UserInteraction model."""

    list_display = ("user", "article_truncated", "action", "created")
    list_filter = ("action", "created", "article__source")
    search_fields = ("user__email", "article__title")
    date_hierarchy = "created"
    readonly_fields = ("uuid",)

    def article_truncated(self, obj):
        """Truncated article title."""
        return (
            obj.article.title[:40] + "..."
            if len(obj.article.title) > 40
            else obj.article.title
        )

    article_truncated.short_description = _("Article")


@admin.register(SearchAnalytics)
class SearchAnalyticsAdmin(admin.ModelAdmin):
    """Admin configuration for SearchAnalytics model."""

    list_display = (
        "query",
        "user",
        "result_count",
        "search_type",
        "response_time_ms",
        "created",
    )
    list_filter = ("search_type", "created", "result_count")
    search_fields = ("query", "normalized_query", "user__email")
    date_hierarchy = "created"
    readonly_fields = ("uuid",)

    def get_queryset(self, request):
        """Optimize queryset with user selection."""
        return super().get_queryset(request).select_related("user")


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    """Admin configuration for UserPreference model."""

    list_display = (
        "user",
        "preferred_categories_display",
        "preferred_sources_display",
        "created",
    )
    list_filter = ("created", "modified")
    search_fields = ("user__email",)
    readonly_fields = ("created", "modified")
    filter_horizontal = ("preferred_categories", "preferred_sources")

    def preferred_categories_display(self, obj):
        """Display preferred categories."""
        categories = obj.preferred_categories.all()
        return ", ".join([cat.name for cat in categories]) if categories else "-"

    preferred_categories_display.short_description = _("Preferred Categories")

    def preferred_sources_display(self, obj):
        """Display preferred sources count."""
        return f"{obj.preferred_sources.count()} sources"

    preferred_sources_display.short_description = _("Preferred Sources")


@admin.register(BookmarkedArticle)
class BookmarkedArticleAdmin(admin.ModelAdmin):
    """Admin configuration for BookmarkedArticle model."""

    list_display = ("user", "article_truncated", "created")
    list_filter = ("created", "article__source")
    search_fields = ("user__email", "article__title")
    date_hierarchy = "created"
    readonly_fields = ("created", "modified")

    def article_truncated(self, obj):
        """Truncated article title."""
        return (
            obj.article.title[:50] + "..."
            if len(obj.article.title) > 50
            else obj.article.title
        )

    article_truncated.short_description = _("Article")


@admin.register(LikedArticle)
class LikedArticleAdmin(admin.ModelAdmin):
    """Admin configuration for LikedArticle model."""

    list_display = ("user", "article_truncated", "created")
    list_filter = ("created", "article__source")
    search_fields = ("user__email", "article__title")
    date_hierarchy = "created"
    readonly_fields = ("created", "modified")

    def article_truncated(self, obj):
        """Truncated article title."""
        return (
            obj.article.title[:50] + "..."
            if len(obj.article.title) > 50
            else obj.article.title
        )

    article_truncated.short_description = _("Article")


# Admin site customization
admin.site.site_header = _("NewsFlow Administration")
admin.site.site_title = _("NewsFlow Admin")
admin.site.index_title = _("Welcome to NewsFlow Administration")
