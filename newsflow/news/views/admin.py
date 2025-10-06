"""
Admin dashboard views for NewsFlow application.

Provides comprehensive administrative interface with metrics, analytics,
user management, and content moderation tools.
"""

from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Avg
from django.db.models import Count
from django.db.models import Q
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.db.models.functions import TruncHour
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic import TemplateView

from ..models import Article
from ..models import BookmarkedArticle
from ..models import CategoryChoices
from ..models import LikedArticle
from ..models import NewsSource
from ..models import SearchAnalytics
from ..models import UserInteraction

User = get_user_model()


class StaffRequiredMixin(UserPassesTestMixin):
    """Mixin to require staff access for admin views."""

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff


@method_decorator(staff_member_required, name="dispatch")
class AdminDashboardView(StaffRequiredMixin, TemplateView):
    """Main admin dashboard with overview metrics."""

    template_name = "admin/dashboard/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Time ranges for analysis
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)

        # Basic statistics
        context.update(
            {
                "total_articles": Article.objects.count(),
                "published_articles": Article.objects.published().count(),
                "total_sources": NewsSource.objects.count(),
                "active_sources": NewsSource.objects.active().count(),
                "total_users": User.objects.count(),
                "total_interactions": UserInteraction.objects.count(),
            },
        )

        # Recent activity (last 24 hours)
        context.update(
            {
                "articles_last_24h": Article.objects.filter(
                    created__gte=last_24h,
                ).count(),
                "users_last_24h": User.objects.filter(
                    date_joined__gte=last_24h,
                ).count(),
                "interactions_last_24h": UserInteraction.objects.filter(
                    created__gte=last_24h,
                ).count(),
                "searches_last_24h": SearchAnalytics.objects.filter(
                    created__gte=last_24h,
                ).count(),
            },
        )

        # Top performing content
        context.update(
            {
                "top_articles": Article.objects.published().order_by("-view_count")[
                    :10
                ],
                "top_sources": NewsSource.objects.active().order_by(
                    "-total_articles_scraped",
                )[:10],
                "recent_searches": SearchAnalytics.objects.successful_searches().order_by(
                    "-created",
                )[:10],
            },
        )

        # User engagement metrics
        bookmark_count = BookmarkedArticle.objects.count()
        like_count = LikedArticle.objects.count()
        share_count = UserInteraction.objects.filter(action="share").count()

        context.update(
            {
                "bookmark_count": bookmark_count,
                "like_count": like_count,
                "share_count": share_count,
                "engagement_total": bookmark_count + like_count + share_count,
            },
        )

        # Category distribution
        category_stats = (
            Article.objects.published()
            .values(
                "source__primary_category",
            )
            .annotate(
                count=Count("id"),
            )
            .order_by("-count")[:8]
        )

        context["category_stats"] = category_stats

        # Sentiment analysis overview
        sentiment_stats = (
            Article.objects.published()
            .exclude(
                sentiment_label__isnull=True,
            )
            .values("sentiment_label")
            .annotate(
                count=Count("id"),
            )
        )

        context["sentiment_stats"] = sentiment_stats

        return context


@method_decorator(staff_member_required, name="dispatch")
class AdminAnalyticsView(StaffRequiredMixin, TemplateView):
    """Detailed analytics and reporting dashboard."""

    template_name = "admin/dashboard/analytics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Time range selection
        time_range = self.request.GET.get("range", "7d")

        if time_range == "24h":
            start_date = timezone.now() - timedelta(hours=24)
            group_by = TruncHour
        elif time_range == "30d":
            start_date = timezone.now() - timedelta(days=30)
            group_by = TruncDate
        else:  # 7d default
            start_date = timezone.now() - timedelta(days=7)
            group_by = TruncDate

        context["time_range"] = time_range

        # Article publication trends
        article_trends = (
            Article.objects.filter(
                published_at__gte=start_date,
            )
            .annotate(
                date=group_by("published_at"),
            )
            .values("date")
            .annotate(
                count=Count("id"),
            )
            .order_by("date")
        )

        context["article_trends"] = list(article_trends)

        # User interaction trends
        interaction_trends = (
            UserInteraction.objects.filter(
                created__gte=start_date,
            )
            .annotate(
                date=group_by("created"),
            )
            .values("date", "action")
            .annotate(
                count=Count("id"),
            )
            .order_by("date", "action")
        )

        context["interaction_trends"] = list(interaction_trends)

        # Search analytics
        search_trends = (
            SearchAnalytics.objects.filter(
                created__gte=start_date,
            )
            .annotate(
                date=group_by("created"),
            )
            .values("date")
            .annotate(
                count=Count("id"),
                avg_results=Avg("result_count"),
            )
            .order_by("date")
        )

        context["search_trends"] = list(search_trends)

        # Popular search terms
        popular_searches = (
            SearchAnalytics.objects.filter(
                created__gte=start_date,
                result_count__gt=0,
            )
            .values("normalized_query")
            .annotate(
                search_count=Count("id"),
                avg_results=Avg("result_count"),
            )
            .order_by("-search_count")[:20]
        )

        context["popular_searches"] = popular_searches

        # Source performance
        source_performance = (
            NewsSource.objects.filter(
                articles__published_at__gte=start_date,
            )
            .annotate(
                articles_count=Count("articles"),
                avg_views=Avg("articles__view_count"),
                total_views=Sum("articles__view_count"),
            )
            .order_by("-total_views")[:15]
        )

        context["source_performance"] = source_performance

        return context


@method_decorator(staff_member_required, name="dispatch")
class AdminUsersView(StaffRequiredMixin, TemplateView):
    """User management and analytics dashboard."""

    template_name = "admin/dashboard/users.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # User statistics
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)

        context.update(
            {
                "total_users": User.objects.count(),
                "active_users_24h": User.objects.filter(
                    last_login__gte=last_24h,
                ).count(),
                "new_users_7d": User.objects.filter(date_joined__gte=last_7d).count(),
                "new_users_30d": User.objects.filter(date_joined__gte=last_30d).count(),
            },
        )

        # User registration trends
        registration_trends = (
            User.objects.filter(
                date_joined__gte=last_30d,
            )
            .annotate(
                date=TruncDate("date_joined"),
            )
            .values("date")
            .annotate(
                count=Count("id"),
            )
            .order_by("date")
        )

        context["registration_trends"] = list(registration_trends)

        # Most active users (by interactions)
        active_users = User.objects.annotate(
            interaction_count=Count("interactions"),
            bookmark_count=Count("bookmarks"),
            like_count=Count("liked_articles"),
        ).order_by("-interaction_count")[:20]

        context["active_users"] = active_users

        # User search behavior
        search_stats = (
            SearchAnalytics.objects.filter(
                user__isnull=False,
                created__gte=last_7d,
            )
            .values("user__email")
            .annotate(
                search_count=Count("id"),
                avg_results=Avg("result_count"),
            )
            .order_by("-search_count")[:15]
        )

        context["search_stats"] = search_stats

        # Pagination for user list
        users_list = User.objects.select_related().order_by("-date_joined")
        paginator = Paginator(users_list, 25)
        page = self.request.GET.get("page", 1)
        users = paginator.get_page(page)

        context["users"] = users

        return context


@method_decorator(staff_member_required, name="dispatch")
class AdminContentView(StaffRequiredMixin, ListView):
    """Content management and moderation dashboard with filtering and pagination."""

    template_name = "admin/dashboard/content.html"
    model = Article
    context_object_name = "articles"
    paginate_by = 20

    def get_queryset(self):
        """Get filtered queryset based on query parameters."""
        queryset = (
            Article.objects.select_related("source")
            .prefetch_related("categories")
            .order_by("-created")
        )

        # Get filter parameters
        category = self.request.GET.get("category")
        status = self.request.GET.get("status")
        source = self.request.GET.get("source")
        search = self.request.GET.get("search")

        # Apply category filter
        if category and category != "all":
            if category in dict(CategoryChoices.choices).keys():
                queryset = queryset.filter(
                    Q(source__primary_category=category) | Q(categories__slug=category),
                ).distinct()

        # Apply status filter
        if status == "published":
            queryset = queryset.filter(is_published=True)
        elif status == "draft":
            queryset = queryset.filter(is_published=False)
        elif status == "featured":
            queryset = queryset.filter(is_featured=True)

        # Apply source filter
        if source:
            queryset = queryset.filter(source_id=source)

        # Apply search filter
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(content__icontains=search)
                | Q(author__icontains=search),
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Content statistics
        now = timezone.now()
        last_24h = now - timedelta(hours=24)

        context.update(
            {
                "total_articles": Article.objects.count(),
                "published_articles": Article.objects.published().count(),
                "draft_articles": Article.objects.filter(is_published=False).count(),
                "featured_articles": Article.objects.filter(is_featured=True).count(),
                "articles_last_24h": Article.objects.filter(
                    created__gte=last_24h,
                ).count(),
            },
        )

        # Content quality metrics
        quality_metrics = {
            "articles_with_images": Article.objects.published()
            .exclude(top_image="")
            .count(),
            "articles_with_summaries": Article.objects.published()
            .exclude(summary="")
            .count(),
            "articles_with_keywords": Article.objects.published()
            .exclude(keywords=[])
            .count(),
            "articles_with_sentiment": Article.objects.published()
            .exclude(sentiment_label__isnull=True)
            .count(),
        }

        context["quality_metrics"] = quality_metrics

        # Filter options
        context["category_choices"] = [("all", "All Categories")] + list(
            CategoryChoices.choices,
        )
        context["status_choices"] = [
            ("all", "All Status"),
            ("published", "Published"),
            ("draft", "Draft"),
            ("featured", "Featured"),
        ]
        context["sources"] = NewsSource.objects.active().order_by("name")

        # Current filter values
        context["current_category"] = self.request.GET.get("category", "all")
        context["current_status"] = self.request.GET.get("status", "all")
        context["current_source"] = self.request.GET.get("source", "")
        context["current_search"] = self.request.GET.get("search", "")

        # Filtered counts
        total_filtered = self.get_queryset().count()
        context["total_filtered"] = total_filtered

        return context


@method_decorator(staff_member_required, name="dispatch")
class AdminSearchAnalyticsView(StaffRequiredMixin, ListView):
    """Search analytics dashboard with filtering and pagination."""

    template_name = "admin/dashboard/search_analytics.html"
    model = SearchAnalytics
    context_object_name = "searches"
    paginate_by = 25

    def get_queryset(self):
        """Get filtered queryset based on query parameters."""
        queryset = SearchAnalytics.objects.select_related("user").order_by("-created")

        # Get filter parameters
        search_type = self.request.GET.get("search_type")
        user_filter = self.request.GET.get("user_filter")
        date_filter = self.request.GET.get("date_filter")
        query_search = self.request.GET.get("query_search")

        # Apply search type filter
        if search_type and search_type != "all":
            queryset = queryset.filter(search_type=search_type)

        # Apply user filter
        if user_filter == "registered":
            queryset = queryset.filter(user__isnull=False)
        elif user_filter == "anonymous":
            queryset = queryset.filter(user__isnull=True)

        # Apply date filter
        now = timezone.now()
        if date_filter == "today":
            queryset = queryset.filter(created__gte=now - timedelta(hours=24))
        elif date_filter == "week":
            queryset = queryset.filter(created__gte=now - timedelta(days=7))
        elif date_filter == "month":
            queryset = queryset.filter(created__gte=now - timedelta(days=30))

        # Apply query search
        if query_search:
            queryset = queryset.filter(
                Q(query__icontains=query_search)
                | Q(normalized_query__icontains=query_search),
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Search statistics
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        total_searches = SearchAnalytics.objects.count()
        searches_24h = SearchAnalytics.objects.filter(created__gte=last_24h).count()
        successful_searches = SearchAnalytics.objects.filter(result_count__gt=0).count()
        avg_results = (
            SearchAnalytics.objects.filter(result_count__gt=0).aggregate(
                avg_results=Avg("result_count"),
            )["avg_results"]
            or 0
        )

        context.update(
            {
                "total_searches": total_searches,
                "searches_24h": searches_24h,
                "successful_searches": successful_searches,
                "success_rate": (successful_searches / total_searches * 100)
                if total_searches > 0
                else 0,
                "avg_results": round(avg_results, 1),
            },
        )

        # Popular queries
        popular_queries = (
            SearchAnalytics.objects.filter(
                created__gte=last_7d,
                result_count__gt=0,
            )
            .values("normalized_query")
            .annotate(
                search_count=Count("id"),
                avg_results=Avg("result_count"),
            )
            .order_by("-search_count")[:10]
        )

        context["popular_queries"] = popular_queries

        # Filter options
        context["search_type_choices"] = [
            ("all", "All Types"),
            ("article", "Article Search"),
            ("autocomplete", "Autocomplete"),
            ("trending", "Trending Search"),
        ]
        context["user_filter_choices"] = [
            ("all", "All Users"),
            ("registered", "Registered Users"),
            ("anonymous", "Anonymous Users"),
        ]
        context["date_filter_choices"] = [
            ("all", "All Time"),
            ("today", "Last 24 Hours"),
            ("week", "Last 7 Days"),
            ("month", "Last 30 Days"),
        ]

        # Current filter values
        context["current_search_type"] = self.request.GET.get("search_type", "all")
        context["current_user_filter"] = self.request.GET.get("user_filter", "all")
        context["current_date_filter"] = self.request.GET.get("date_filter", "all")
        context["current_query_search"] = self.request.GET.get("query_search", "")

        # Filtered counts
        total_filtered = self.get_queryset().count()
        context["total_filtered"] = total_filtered

        return context
