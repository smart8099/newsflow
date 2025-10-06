"""
Personalized "For You" views for news app.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.views.generic import TemplateView

from ..models import Article
from ..models import CategoryChoices
from ..models import NewsSource
from ..models import UserInteraction


class ForYouView(TemplateView):
    """
    Personalized news feed based on user preferences and behavior.
    """

    template_name = "news/for_you.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if user needs onboarding first
        show_onboarding = False
        user_needs_onboarding = False

        if self.request.user.is_authenticated:
            try:
                profile = self.request.user.profile
                user_needs_onboarding = (
                    profile.needs_onboarding() or not profile.has_preferences()
                )
                show_onboarding = user_needs_onboarding
            except:
                user_needs_onboarding = True
                show_onboarding = True

        # Only get articles if user doesn't need onboarding
        if not self.request.user.is_authenticated:
            # For anonymous users, show general trending content
            recommended_articles = (
                Article.objects.published()
                .filter(
                    published_at__gte=timezone.now() - timedelta(hours=48),
                )
                .order_by("-view_count", "-published_at")[:20]
            )
        elif user_needs_onboarding:
            # User needs onboarding - don't show any articles
            recommended_articles = Article.objects.none()
        else:
            # Get personalized recommendations with filters applied
            recommended_articles = self._get_personalized_recommendations()

        # Get user's reading history if authenticated
        recently_read = []
        if self.request.user.is_authenticated:
            try:
                from ..models import ReadArticle

                recently_read = (
                    ReadArticle.objects.filter(
                        user=self.request.user,
                    )
                    .select_related("article__source")
                    .order_by("-created")[:5]
                )
            except:
                pass

        # Get trending articles for sidebar
        trending_articles = (
            Article.objects.published()
            .filter(
                published_at__gte=timezone.now() - timedelta(hours=24),
            )
            .order_by("-view_count")[:8]
        )

        # Get recommended sources based on user activity
        recommended_sources = self._get_recommended_sources()

        # Onboarding check already done above

        # Get data for onboarding modal
        available_categories = CategoryChoices.choices
        popular_sources = NewsSource.objects.active().order_by(
            "-credibility_score",
            "-total_articles_scraped",
        )[:20]

        # Get filter data based on user preferences
        filter_categories = []
        filter_sources = []

        if self.request.user.is_authenticated and not user_needs_onboarding:
            try:
                profile = self.request.user.profile
                # Get categories from user preferences
                user_categories = profile.preferred_categories.all()
                filter_categories = [(cat.slug, cat.name) for cat in user_categories]

                # Get sources from user preferences
                filter_sources = profile.preferred_sources.all()
            except:
                # Fallback to all categories if no preferences
                filter_categories = CategoryChoices.choices
                filter_sources = NewsSource.objects.active()[:10]

        context.update(
            {
                "recommended_articles": recommended_articles,
                "recently_read": recently_read,
                "trending_articles": trending_articles,
                "recommended_sources": recommended_sources,
                "is_personalized": self.request.user.is_authenticated,
                "show_onboarding": show_onboarding,
                "show_login_prompt": not self.request.user.is_authenticated,
                "category_choices": CategoryChoices.choices,
                "available_categories": available_categories,
                "popular_sources": popular_sources,
                "filter_categories": filter_categories,
                "filter_sources": filter_sources,
            },
        )

        return context

    def _get_personalized_recommendations(self):
        """Get personalized article recommendations for authenticated user."""
        user = self.request.user

        # Get user's interaction history
        user_interactions = UserInteraction.objects.filter(user=user).values_list(
            "article_id",
            flat=True,
        )

        # Get user preferences from profile
        try:
            profile = user.profile
            preferred_categories = profile.preferred_categories.all()
            preferred_sources = profile.preferred_sources.all()
            # Note: blocked_sources not implemented yet in profile
            blocked_sources = []
        except:
            preferred_categories = []
            preferred_sources = []
            blocked_sources = []

        # Start with base queryset
        queryset = Article.objects.published().exclude(id__in=user_interactions)

        # Apply preferences
        if preferred_categories.exists():
            category_slugs = list(preferred_categories.values_list("slug", flat=True))
            queryset = queryset.filter(
                Q(source__primary_category__in=category_slugs)
                | Q(categories__slug__in=category_slugs),
            ).distinct()

        if preferred_sources.exists():
            queryset = queryset.filter(source__in=preferred_sources)

        if blocked_sources:
            queryset = queryset.exclude(source__in=blocked_sources)

        # If no preferences, use behavior-based recommendations
        if not preferred_categories.exists() and not preferred_sources.exists():
            # Get categories/sources user has interacted with
            interacted_articles = Article.objects.filter(id__in=user_interactions[:50])

            # Get categories from user's interactions
            interacted_categories = list(
                interacted_articles.values_list(
                    "source__primary_category",
                    flat=True,
                ).distinct(),
            )

            # Get sources from user's interactions
            interacted_sources = list(
                interacted_articles.values_list("source", flat=True).distinct(),
            )

            if interacted_categories or interacted_sources:
                queryset = queryset.filter(
                    Q(source__primary_category__in=interacted_categories)
                    | Q(source__in=interacted_sources),
                ).distinct()

        # Apply user filters before slicing
        queryset = self._apply_filters(queryset)

        # Apply default ordering if no sort filter was applied
        sort = self.request.GET.get("sort", "relevance")
        if sort == "relevance":
            queryset = queryset.order_by("-view_count", "-published_at")

        # Order by engagement and recency and slice
        return queryset.select_related("source").prefetch_related("categories")[:20]

    def _get_recommended_sources(self):
        """Get recommended news sources based on user activity."""
        if not self.request.user.is_authenticated:
            return NewsSource.objects.active().order_by("-credibility_score")[:6]

        # Get sources user has interacted with
        user_interactions = UserInteraction.objects.filter(user=self.request.user)
        interacted_sources = user_interactions.values_list(
            "article__source",
            flat=True,
        ).distinct()

        # Get similar sources (same category, high credibility)
        recommended = (
            NewsSource.objects.active()
            .exclude(
                id__in=interacted_sources,
            )
            .filter(
                primary_category__in=NewsSource.objects.filter(
                    id__in=interacted_sources,
                ).values_list("primary_category", flat=True),
            )
            .order_by("-credibility_score", "-total_articles_scraped")[:6]
        )

        return recommended

    def _apply_filters(self, queryset):
        """Apply user-selected filters to the queryset."""
        # Get filter parameters from request
        category = self.request.GET.get("category")
        source = self.request.GET.get("source")
        sentiment = self.request.GET.get("sentiment")
        sort = self.request.GET.get("sort", "relevance")

        # Apply category filter
        if category:
            queryset = queryset.filter(
                Q(source__primary_category=category) | Q(categories__slug=category),
            ).distinct()

        # Apply source filter
        if source:
            queryset = queryset.filter(source__id=source)

        # Apply sentiment filter
        if sentiment:
            queryset = queryset.filter(sentiment_label=sentiment)

        # Apply sorting
        if sort == "latest":
            queryset = queryset.order_by("-published_at")
        elif sort == "popular":
            queryset = queryset.order_by("-view_count", "-published_at")
        # For 'relevance' (default), don't apply ordering here since it's handled in the calling method

        return queryset
