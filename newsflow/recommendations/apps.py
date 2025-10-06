"""
App configuration for recommendations.
"""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RecommendationsConfig(AppConfig):
    """Configuration for the recommendations app."""

    name = "newsflow.recommendations"
    verbose_name = _("Recommendations")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        """Initialize app when Django starts."""
        try:
            # Import signals here to ensure they're registered
            pass
        except ImportError:
            pass
