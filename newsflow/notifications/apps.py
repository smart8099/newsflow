from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "newsflow.notifications"
    verbose_name = "Notifications"

    def ready(self):
        """Import signals when app is ready."""
        import newsflow.notifications.signals  # noqa: F401
