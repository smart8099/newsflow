"""
User preferences management views.
"""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.generic import TemplateView

from ..models import Category
from ..models import CategoryChoices
from ..models import NewsSource


class PreferencesView(LoginRequiredMixin, TemplateView):
    """
    View for users to customize their preferences.
    """

    template_name = "news/preferences.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get user's current preferences
        try:
            profile = self.request.user.profile
            current_categories = profile.preferred_categories.all()
            current_sources = profile.preferred_sources.all()
        except:
            current_categories = []
            current_sources = []

        # Get all available options
        available_categories = CategoryChoices.choices
        all_sources = NewsSource.objects.active().order_by(
            "-credibility_score",
            "-total_articles_scraped",
        )

        context.update(
            {
                "current_categories": current_categories,
                "current_sources": current_sources,
                "available_categories": available_categories,
                "all_sources": all_sources,
            },
        )

        return context


@login_required
def update_preferences(request):
    """
    AJAX endpoint to update user preferences.
    """
    if request.method == "POST":
        try:
            import json

            data = json.loads(request.body)
            categories = data.get("categories", [])
            sources = data.get("sources", [])

            # Get user profile
            user_profile = request.user.profile

            # Get category and source objects
            category_objects = Category.objects.filter(slug__in=categories)
            source_objects = NewsSource.objects.filter(id__in=sources)

            # Update preferences
            user_profile.preferred_categories.set(category_objects)
            user_profile.preferred_sources.set(source_objects)

            return JsonResponse(
                {
                    "status": "success",
                    "message": "Preferences updated successfully",
                },
            )

        except Exception as e:
            return JsonResponse(
                {
                    "status": "error",
                    "message": f"Error updating preferences: {e!s}",
                },
            )

    return JsonResponse({"status": "error", "message": "Invalid request method"})
