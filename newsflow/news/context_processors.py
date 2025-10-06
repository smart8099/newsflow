"""
Context processors for newsflow news application.
"""

from .models import CategoryChoices


def news_context(request):
    """
    Add common news-related context variables to all templates.
    """
    return {
        "category_choices": CategoryChoices.choices,
        "current_category": getattr(request, "current_category", None),
    }
