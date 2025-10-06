import logging
from datetime import datetime
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template import Context
from django.template import Template
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Notification
from .models import NotificationChannel
from .models import NotificationStatus
from .models import NotificationType
from .tasks import send_password_reset_email_task
from .tasks import send_verification_email_task
from .tasks import send_welcome_email_task

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications via different channels."""

    @staticmethod
    def send_email_verification(user: User, verification_url: str) -> Notification:
        """Send email verification notification synchronously."""
        context = {
            "user": user,
            "verification_url": verification_url,
            "site_name": getattr(settings, "SITE_NAME", "Newsflow"),
            "frontend_url": getattr(settings, "FRONTEND_URL", "http://localhost:8000"),
            "current_year": datetime.now().year,
        }

        return NotificationService._send_email_notification(
            user=user,
            notification_type=NotificationType.EMAIL_VERIFICATION,
            template_name="verification_email",
            context=context,
            subject_template="Verify your email address for {{ site_name }}",
        )

    @staticmethod
    def send_welcome_email(user: User) -> Notification:
        """Send welcome email after successful registration synchronously."""
        context = {
            "user": user,
            "site_name": getattr(settings, "SITE_NAME", "Newsflow"),
            "login_url": getattr(settings, "FRONTEND_URL", "http://localhost:8000")
            + "/accounts/login/",
            "frontend_url": getattr(settings, "FRONTEND_URL", "http://localhost:8000"),
            "current_year": datetime.now().year,
        }

        return NotificationService._send_email_notification(
            user=user,
            notification_type=NotificationType.WELCOME,
            template_name="welcome_email",
            context=context,
            subject_template="Welcome to {{ site_name }}! Your news journey begins now",
        )

    @staticmethod
    def send_password_reset(user: User, reset_url: str) -> Notification:
        """Send password reset notification synchronously."""
        context = {
            "user": user,
            "reset_url": reset_url,
            "site_name": getattr(settings, "SITE_NAME", "Newsflow"),
            "frontend_url": getattr(settings, "FRONTEND_URL", "http://localhost:8000"),
            "current_year": datetime.now().year,
        }

        return NotificationService._send_email_notification(
            user=user,
            notification_type=NotificationType.PASSWORD_RESET,
            template_name="password_reset_email",
            context=context,
            subject_template="Reset your password for {{ site_name }}",
        )

    # Celery task queueing methods
    @staticmethod
    def queue_email_verification(user: User, verification_url: str) -> str:
        """Queue email verification notification via Celery."""
        task = send_verification_email_task.delay(user.id, verification_url)
        logger.info(f"Queued email verification task {task.id} for user {user.id}")
        return task.id

    @staticmethod
    def queue_welcome_email(user: User) -> str:
        """Queue welcome email notification via Celery."""
        task = send_welcome_email_task.delay(user.id)
        logger.info(f"Queued welcome email task {task.id} for user {user.id}")
        return task.id

    @staticmethod
    def queue_password_reset(user: User, reset_url: str) -> str:
        """Queue password reset notification via Celery."""
        task = send_password_reset_email_task.delay(user.id, reset_url)
        logger.info(f"Queued password reset task {task.id} for user {user.id}")
        return task.id

    @staticmethod
    def _send_email_notification(
        user: User,
        notification_type: str,
        template_name: str,
        context: dict[str, Any],
        subject_template: str,
        recipient_email: str | None = None,
    ) -> Notification:
        """Internal method to send email notifications using file templates."""

        # Create notification record
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            channel=NotificationChannel.EMAIL,
            status=NotificationStatus.PENDING,
            subject="",  # Will be filled after template rendering
            content="",  # Will be filled after template rendering
            recipient_email=recipient_email or user.email,
        )

        try:
            # Render HTML template
            html_content = render_to_string(f"emails/{template_name}.html", context)

            # Render text template
            text_content = render_to_string(f"emails/{template_name}.txt", context)

            # Render subject
            subject_tmpl = Template(subject_template)
            subject = subject_tmpl.render(Context(context))

            # Update notification with rendered content
            notification.subject = subject
            notification.content = html_content
            notification.save()

            # Send email
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=getattr(
                    settings,
                    "DEFAULT_FROM_EMAIL",
                    "noreply@newsflow.com",
                ),
                to=[notification.recipient_email],
            )

            email.attach_alternative(html_content, "text/html")
            email.send()

            # Update notification status
            notification.status = NotificationStatus.SENT
            notification.sent_at = timezone.now()
            notification.save()

            logger.info(f"Email notification sent successfully: {notification.id}")
            return notification

        except Exception as e:
            logger.error(f"Failed to send email notification: {e!s}")

            # Update notification with error
            notification.status = NotificationStatus.FAILED
            notification.error_message = str(e)
            notification.save()

            return notification
