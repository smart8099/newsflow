"""
Bookmarks views for news app.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from ..models import BookmarkedArticle


class BookmarksView(LoginRequiredMixin, ListView):
    """
    User's bookmarked articles view.
    """

    model = BookmarkedArticle
    template_name = "news/bookmarks.html"
    context_object_name = "bookmarked_articles"
    paginate_by = 12

    def get_queryset(self):
        return (
            BookmarkedArticle.objects.filter(
                user=self.request.user,
            )
            .select_related("article__source")
            .prefetch_related("article__categories")
            .order_by("-created")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "total_bookmarks": self.get_queryset().count(),
            },
        )
        return context
