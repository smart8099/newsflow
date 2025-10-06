from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import User
from .models import UserProfile

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


class UserProfileInline(admin.StackedInline):
    """Inline admin for UserProfile."""

    model = UserProfile
    can_delete = False
    verbose_name_plural = _("Profile")
    fields = (
        "uuid",
        "theme_preference",
        "reading_speed",
        # "preferred_categories",  # Will be added in later migration
        "notification_preferences",
    )
    readonly_fields = ("uuid",)
    # filter_horizontal = ("preferred_categories",)  # Will be added in later migration


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    inlines = (UserProfileInline,)

    fieldsets = (
        (None, {"fields": ("uuid", "email", "password")}),
        (_("Personal info"), {"fields": ("name",)}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    readonly_fields = ("uuid",)
    list_display = ["email", "name", "theme_preference", "is_superuser", "date_joined"]
    search_fields = ["name", "email"]
    ordering = ["email"]
    list_filter = ["is_staff", "is_superuser", "is_active", "date_joined"]

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )

    def theme_preference(self, obj):
        """Show user's theme preference from profile."""
        if hasattr(obj, "profile"):
            return obj.profile.get_theme_preference_display()
        return _("No profile")

    theme_preference.short_description = _("Theme")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin configuration for UserProfile."""

    list_display = (
        "user_email",
        "theme_preference",
        "reading_speed",
        "preferred_categories_count",
        "reading_history_count",
        "bookmarked_count",
        "created",
    )

    list_filter = (
        "theme_preference",
        "created",
        # "preferred_categories",  # Will be added in later migration
    )

    search_fields = (
        "user__email",
        "user__name",
    )

    readonly_fields = (
        "uuid",
        "user",  # Don't allow changing user after creation
        "created",
        "modified",
        "reading_history_count",
        "bookmarked_count",
        "recommended_articles_count",
    )

    fieldsets = (
        (
            _("Basic Information"),
            {
                "fields": ("uuid", "user"),
            },
        ),
        (
            _("Preferences"),
            {
                "fields": (
                    "theme_preference",
                    "reading_speed",
                    # "preferred_categories",  # Will be added in later migration
                ),
            },
        ),
        (
            _("Notifications"),
            {
                "fields": ("notification_preferences",),
                "classes": ("collapse",),
            },
        ),
        (
            _("Statistics"),
            {
                "fields": (
                    "reading_history_count",
                    "bookmarked_count",
                    "recommended_articles_count",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ("created", "modified"),
                "classes": ("collapse",),
            },
        ),
    )

    # filter_horizontal = ("preferred_categories",)  # Will be added in later migration

    def user_email(self, obj):
        """Show user email."""
        return obj.user.email

    user_email.short_description = _("User")
    user_email.admin_order_field = "user__email"

    def preferred_categories_count(self, obj):
        """Show count of preferred categories."""
        return obj.preferred_categories.count()

    preferred_categories_count.short_description = _("Categories")

    def reading_history_count(self, obj):
        """Show reading history count."""
        return obj.get_reading_history_count()

    reading_history_count.short_description = _("Articles Read")

    def bookmarked_count(self, obj):
        """Show bookmarked articles count."""
        return obj.get_bookmarked_articles_count()

    bookmarked_count.short_description = _("Bookmarked")

    def recommended_articles_count(self, obj):
        """Show recommended articles count."""
        return obj.get_recommended_articles_count()

    recommended_articles_count.short_description = _("Recommended Today")

    def has_add_permission(self, request):
        """Disable manual creation of profiles (auto-created via signal)."""
        return False
