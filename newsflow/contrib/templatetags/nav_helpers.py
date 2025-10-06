from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def active_nav(context, url_name):
    """Return 'active' class if the current path matches the URL name."""
    request = context.get("request")
    if not request:
        return ""

    try:
        current_path = request.path
        url_path = reverse(url_name)

        # Check for exact match or if current path starts with the URL path
        if current_path == url_path or (
            url_name == "news:home" and current_path == "/"
        ):
            return "active"

    except Exception:
        pass

    return ""


@register.simple_tag(takes_context=True)
def active_nav_profile(context, user_uuid):
    """Return 'active' class if the current path matches the user profile URL."""
    request = context.get("request")
    if not request:
        return ""

    try:
        current_path = request.path
        url_path = reverse("users:detail", kwargs={"uuid": user_uuid})

        if current_path == url_path:
            return "active"
    except Exception:
        pass

    return ""
