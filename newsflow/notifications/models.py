from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

User = get_user_model()


class NotificationType(models.TextChoices):
    """Types of notifications."""

    EMAIL_VERIFICATION = "email_verification", _("Email Verification")
    PASSWORD_RESET = "password_reset", _("Password Reset")
    WELCOME = "welcome", _("Welcome")
    NEWS_DIGEST = "news_digest", _("News Digest")
    ACCOUNT_UPDATE = "account_update", _("Account Update")


class NotificationStatus(models.TextChoices):
    """Status of notifications."""

    PENDING = "pending", _("Pending")
    SENT = "sent", _("Sent")
    DELIVERED = "delivered", _("Delivered")
    FAILED = "failed", _("Failed")


class NotificationChannel(models.TextChoices):
    """Channels for sending notifications."""

    EMAIL = "email", _("Email")
    SMS = "sms", _("SMS")
    PUSH = "push", _("Push Notification")
    IN_APP = "in_app", _("In-App Notification")


class Notification(TimeStampedModel):
    """Model to track all notifications sent to users."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("User"),
    )
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        verbose_name=_("Notification Type"),
    )
    channel = models.CharField(
        max_length=20,
        choices=NotificationChannel.choices,
        default=NotificationChannel.EMAIL,
        verbose_name=_("Channel"),
    )
    status = models.CharField(
        max_length=20,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
        verbose_name=_("Status"),
    )
    subject = models.CharField(
        max_length=255,
        verbose_name=_("Subject"),
    )
    content = models.TextField(
        verbose_name=_("Content"),
    )
    recipient_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name=_("Recipient Email"),
    )
    recipient_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name=_("Recipient Phone"),
    )
    sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Sent At"),
    )
    delivered_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_("Delivered At"),
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("Error Message"),
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Metadata"),
        help_text=_("Additional data related to the notification"),
    )

    class Meta:
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["user", "notification_type"]),
            models.Index(fields=["status", "created"]),
            models.Index(fields=["channel", "sent_at"]),
        ]

    def __str__(self):
        return f"{self.get_notification_type_display()} to {self.user.email}"
