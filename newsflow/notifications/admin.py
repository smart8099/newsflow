from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "notification_type",
        "channel",
        "status",
        "subject",
        "sent_at",
        "created",
    ]
    list_filter = [
        "notification_type",
        "channel",
        "status",
        "created",
        "sent_at",
    ]
    search_fields = [
        "user__email",
        "user__name",
        "subject",
        "recipient_email",
    ]
    readonly_fields = [
        "created",
        "modified",
        "sent_at",
        "delivered_at",
    ]
    list_per_page = 50
    date_hierarchy = "created"

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "user",
                    "notification_type",
                    "channel",
                    "status",
                ),
            },
        ),
        (
            "Content",
            {
                "fields": (
                    "subject",
                    "content",
                ),
            },
        ),
        (
            "Recipients",
            {
                "fields": (
                    "recipient_email",
                    "recipient_phone",
                ),
            },
        ),
        (
            "Tracking",
            {
                "fields": (
                    "sent_at",
                    "delivered_at",
                    "error_message",
                    "metadata",
                ),
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created",
                    "modified",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")
