from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import QuerySet
from django.http import HttpResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import UpdateView

from newsflow.users.models import User


class UserDetailView(LoginRequiredMixin, DetailView):
    model = User
    slug_field = "uuid"
    slug_url_kwarg = "uuid"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self) -> str:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user.get_absolute_url()

    def get_object(self, queryset: QuerySet | None = None) -> User:
        assert self.request.user.is_authenticated  # type guard
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self) -> str:
        return reverse("users:detail", kwargs={"uuid": str(self.request.user.uuid)})


user_redirect_view = UserRedirectView.as_view()


@require_POST
def toggle_theme(request):
    """
    Toggle user's theme preference via HTMX.
    Cycles through: system -> light -> dark -> system
    Supports both authenticated and anonymous users.
    """
    # Get current theme from user or session
    if request.user.is_authenticated and hasattr(request.user, "profile"):
        current_theme = request.user.profile.theme_preference
    else:
        current_theme = request.session.get("theme_preference", "system")

    # Three-way cycle: system -> light -> dark -> system
    if current_theme == "system":
        new_theme = "light"
    elif current_theme == "light":
        new_theme = "dark"
    else:  # dark
        new_theme = "system"

    # Save preference
    if request.user.is_authenticated and hasattr(request.user, "profile"):
        request.user.profile.theme_preference = new_theme
        request.user.profile.save(update_fields=["theme_preference"])
    else:
        request.session["theme_preference"] = new_theme

    # Return empty response for HTMX (prevents JSON display)
    return HttpResponse("")
