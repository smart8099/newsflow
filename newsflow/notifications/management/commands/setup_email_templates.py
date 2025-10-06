from django.core.management.base import BaseCommand

from newsflow.notifications.services import NotificationService


class Command(BaseCommand):
    help = "Set up default email templates for notifications"

    def handle(self, *args, **options):
        self.stdout.write("Setting up default email templates...")

        NotificationService.create_default_templates()

        self.stdout.write(
            self.style.SUCCESS("✅ Default email templates created successfully!"),
        )
