from allauth.account.signals import email_confirmed
from django.dispatch import receiver

from .services import NotificationService


@receiver(email_confirmed)
def send_welcome_email_on_confirmation(sender, request, email_address, **kwargs):
    """Send welcome email when email address is confirmed."""
    NotificationService.send_welcome_email(user=email_address.user)
