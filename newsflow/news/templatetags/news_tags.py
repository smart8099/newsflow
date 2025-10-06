"""
Custom template tags for news app.
"""

from django import template

register = template.Library()


@register.simple_tag
def is_bookmarked(article, user):
    """Check if an article is bookmarked by a user."""
    if not user or not user.is_authenticated:
        return False
    return article.is_bookmarked_by(user)


@register.simple_tag
def is_liked(article, user):
    """Check if an article is liked by a user."""
    if not user or not user.is_authenticated:
        return False
    return article.is_liked_by(user)
