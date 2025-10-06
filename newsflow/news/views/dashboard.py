"""
User dashboard view for NewsFlow application.

Provides a centralized view for users to manage their liked, bookmarked,
and shared articles.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.views.generic import TemplateView

from ..models import Article
from ..models import UserInteraction


class UserDashboardView(LoginRequiredMixin, TemplateView):
    """Dashboard view showing user's liked, bookmarked, and shared articles."""

    template_name = "news/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get the active tab from query params
        active_tab = self.request.GET.get("tab", "bookmarks")
        context["active_tab"] = active_tab

        # Get page number for pagination
        page = self.request.GET.get("page", 1)

        if active_tab == "bookmarks":
            articles_list = self.get_bookmarked_articles(user)
            context["page_title"] = "Bookmarked Articles"
        elif active_tab == "likes":
            articles_list = self.get_liked_articles(user)
            context["page_title"] = "Liked Articles"
        elif active_tab == "shared":
            articles_list = self.get_shared_articles(user)
            context["page_title"] = "Shared Articles"
        else:
            articles_list = self.get_bookmarked_articles(user)
            context["page_title"] = "Bookmarked Articles"

        # Pagination
        paginator = Paginator(articles_list, 12)  # 12 articles per page
        articles = paginator.get_page(page)

        context["articles"] = articles
        context["total_count"] = paginator.count

        # Add counts for each tab
        context["bookmark_count"] = self.get_bookmarked_articles(user).count()
        context["like_count"] = self.get_liked_articles(user).count()
        context["share_count"] = self.get_shared_articles(user).count()

        return context

    def get_bookmarked_articles(self, user):
        """Get user's bookmarked articles."""
        return (
            Article.objects.filter(
                bookmarked_by__user=user,
            )
            .select_related("source")
            .prefetch_related("categories")
            .order_by("-bookmarked_by__created")
        )

    def get_liked_articles(self, user):
        """Get user's liked articles."""
        return (
            Article.objects.filter(
                liked_by__user=user,
            )
            .select_related("source")
            .prefetch_related("categories")
            .order_by("-liked_by__created")
        )

    def get_shared_articles(self, user):
        """Get user's shared articles."""
        # Get articles that the user has shared via UserInteraction
        shared_article_ids = (
            UserInteraction.objects.filter(
                user=user,
                action=UserInteraction.ActionType.SHARE,
            )
            .values_list("article_id", flat=True)
            .distinct()
        )

        return (
            Article.objects.filter(
                id__in=shared_article_ids,
            )
            .select_related("source")
            .prefetch_related("categories")
            .order_by("-interactions__created")
        )
