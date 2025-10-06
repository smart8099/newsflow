"""
Category view for news app.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.views.generic import ListView

from ..models import Article
from ..models import CategoryChoices
from ..models import NewsSource


class CategoryNewsView(ListView):
    """
    Category-specific news view with filtering and pagination.
    """

    model = Article
    template_name = "news/category_list.html"
    context_object_name = "articles"
    paginate_by = 12

    def get_queryset(self):
        category = self.kwargs.get("category", "all")
        queryset = (
            Article.objects.published()
            .select_related("source")
            .prefetch_related("categories")
        )

        if category != "all":
            queryset = queryset.filter(
                Q(source__primary_category=category) | Q(categories__slug=category),
            ).distinct()

        # Apply filters from GET parameters
        sentiment = self.request.GET.get("sentiment")
        if sentiment:
            queryset = queryset.filter(sentiment_label=sentiment)

        source_id = self.request.GET.get("source")
        if source_id:
            queryset = queryset.filter(source_id=source_id)

        date_from = self.request.GET.get("date_from")
        if date_from:
            queryset = queryset.filter(published_at__date__gte=date_from)

        date_to = self.request.GET.get("date_to")
        if date_to:
            queryset = queryset.filter(published_at__date__lte=date_to)

        # Sorting
        sort_by = self.request.GET.get("sort", "latest")
        if sort_by == "popular":
            queryset = queryset.order_by("-view_count", "-published_at")
        elif sort_by == "trending":
            # Trending in last 24 hours
            yesterday = timezone.now() - timedelta(hours=24)
            queryset = queryset.filter(published_at__gte=yesterday).order_by(
                "-view_count",
            )
        else:  # latest
            queryset = queryset.order_by("-published_at")

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.kwargs.get("category", "all")

        # Get category display name
        if category == "all":
            category_name = "All News"
        else:
            category_choices = dict(CategoryChoices.choices)
            category_name = category_choices.get(category, category.title())

        # Get available sources for filtering
        queryset = self.get_queryset()
        base_queryset = Article.objects.published()

        if category != "all":
            base_queryset = base_queryset.filter(
                Q(source__primary_category=category) | Q(categories__slug=category),
            ).distinct()

        available_sources = (
            NewsSource.objects.filter(
                articles__in=base_queryset,
            )
            .distinct()
            .order_by("name")
        )

        # Get trending articles in this category
        trending_in_category = []
        if category != "all":
            trending_in_category = (
                Article.objects.published()
                .filter(
                    Q(source__primary_category=category) | Q(categories__slug=category),
                    published_at__gte=timezone.now() - timedelta(hours=24),
                )
                .distinct()
                .order_by("-view_count")[:5]
            )

        # Applied filters for display
        applied_filters = {
            "sentiment": self.request.GET.get("sentiment"),
            "source": self.request.GET.get("source"),
            "date_from": self.request.GET.get("date_from"),
            "date_to": self.request.GET.get("date_to"),
            "sort": self.request.GET.get("sort", "latest"),
        }

        context.update(
            {
                "current_category": category,
                "category_name": category_name,
                "available_sources": available_sources,
                "trending_in_category": trending_in_category,
                "applied_filters": applied_filters,
            },
        )

        return context
