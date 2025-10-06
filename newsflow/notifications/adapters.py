from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse

from .services import NotificationService


class CustomAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter to use our notification service."""

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        """Override to use our notification service for email verification."""
        # Build the verification URL
        activate_url = self.get_email_confirmation_url(request, emailconfirmation)

        # Send using our notification service
        NotificationService.send_email_verification(
            user=emailconfirmation.email_address.user,
            verification_url=activate_url,
        )

    def get_email_confirmation_url(self, request, emailconfirmation):
        """Build the email confirmation URL."""
        url = reverse("account_confirm_email", args=[emailconfirmation.key])
        return request.build_absolute_uri(url)

    def confirm_email(self, request, email_address):
        """Called when email is confirmed - send welcome email."""
        # Call the parent method first
        super().confirm_email(request, email_address)

        # Send welcome email
        NotificationService.send_welcome_email(user=email_address.user)
