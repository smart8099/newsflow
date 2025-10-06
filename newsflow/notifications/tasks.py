import logging
from datetime import datetime

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Notification
from .models import NotificationChannel
from .models import NotificationStatus
from .models import NotificationType

User = get_user_model()
logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_verification_email_task(self, user_id: int, verification_url: str):
    """Send email verification notification via Celery."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found")
        return False

    return _send_email_task(
        user=user,
        notification_type=NotificationType.EMAIL_VERIFICATION,
        template_name="verification_email",
        context={
            "user": user,
            "verification_url": verification_url,
            "site_name": getattr(settings, "SITE_NAME", "Newsflow"),
            "frontend_url": getattr(settings, "FRONTEND_URL", "http://localhost:8000"),
            "current_year": datetime.now().year,
        },
        subject_template="Verify your email address for {{ site_name }}",
        task_instance=self,
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email_task(self, user_id: int):
    """Send welcome email notification via Celery."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found")
        return False

    login_url = (
        getattr(settings, "FRONTEND_URL", "http://localhost:8000") + "/accounts/login/"
    )

    return _send_email_task(
        user=user,
        notification_type=NotificationType.WELCOME,
        template_name="welcome_email",
        context={
            "user": user,
            "login_url": login_url,
            "site_name": getattr(settings, "SITE_NAME", "Newsflow"),
            "frontend_url": getattr(settings, "FRONTEND_URL", "http://localhost:8000"),
            "current_year": datetime.now().year,
        },
        subject_template="Welcome to {{ site_name }}! Your news journey begins now",
        task_instance=self,
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email_task(self, user_id: int, reset_url: str):
    """Send password reset notification via Celery."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found")
        return False

    return _send_email_task(
        user=user,
        notification_type=NotificationType.PASSWORD_RESET,
        template_name="password_reset_email",
        context={
            "user": user,
            "reset_url": reset_url,
            "site_name": getattr(settings, "SITE_NAME", "Newsflow"),
            "frontend_url": getattr(settings, "FRONTEND_URL", "http://localhost:8000"),
            "current_year": datetime.now().year,
        },
        subject_template="Reset your password for {{ site_name }}",
        task_instance=self,
    )


def _send_email_task(
    user: User,
    notification_type: str,
    template_name: str,
    context: dict,
    subject_template: str,
    task_instance: object | None = None,
    recipient_email: str | None = None,
) -> bool:
    """Internal function to send email using file-based templates."""

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
        from django.template import Context
        from django.template import Template

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
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@newsflow.com"),
            to=[notification.recipient_email],
        )

        email.attach_alternative(html_content, "text/html")
        email.send()

        # Update notification status
        notification.status = NotificationStatus.SENT
        notification.sent_at = timezone.now()
        notification.save()

        logger.info(f"Email notification sent successfully: {notification.id}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email notification: {e!s}")

        # Update notification with error
        notification.status = NotificationStatus.FAILED
        notification.error_message = str(e)
        notification.save()

        # Retry the task if we have a task instance and retries left
        if task_instance and task_instance.request.retries < task_instance.max_retries:
            logger.info(
                f"Retrying email send (attempt {task_instance.request.retries + 1})",
            )
            # Exponential backoff: 60s, 120s, 240s
            countdown = task_instance.default_retry_delay * (
                2**task_instance.request.retries
            )
            raise task_instance.retry(countdown=countdown, exc=e)

        return False


@shared_task
def cleanup_old_notifications():
    """Cleanup old notification records (run periodically)."""
    from datetime import timedelta

    # Delete notifications older than 90 days
    cutoff_date = timezone.now() - timedelta(days=90)
    deleted_count = Notification.objects.filter(created__lt=cutoff_date).delete()[0]

    logger.info(f"Cleaned up {deleted_count} old notification records")
    return deleted_count
