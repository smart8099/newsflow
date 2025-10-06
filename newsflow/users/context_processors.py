from django.conf import settings


def allauth_settings(request):
    """Expose some settings from django-allauth in templates."""
    return {
        "ACCOUNT_ALLOW_REGISTRATION": settings.ACCOUNT_ALLOW_REGISTRATION,
    }


def theme_context(request):
    """
    Add theme-related context to all templates.

    Returns theme preference for both authenticated and anonymous users.
    """
    if request.user.is_authenticated and hasattr(request.user, "profile"):
        theme_preference = request.user.profile.theme_preference
    else:
        # Get from session for anonymous users, default to 'system'
        theme_preference = request.session.get("theme_preference", "system")

    return {
        "user_theme_preference": theme_preference,
    }
