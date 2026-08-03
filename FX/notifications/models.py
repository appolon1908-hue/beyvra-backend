import uuid

from django.db import models
from users.models import User


class Notifications(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification - {self.name}"


class UserNotifications(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    notification = models.ForeignKey(Notifications, on_delete=models.RESTRICT)
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    is_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification for {self.user_id}"


class UserAlerts(models.Model):
    DIRECTION_CHOICES = (
        ("UP", "UP"),
        ("DOWN", "DOWN"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(User, on_delete=models.RESTRICT)
    asset_id = models.CharField(max_length=255)
    price_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    direction = models.CharField(choices=DIRECTION_CHOICES, max_length=5)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Alert for {self.user_id}"


class AdminNotifications(models.Model):
    """Model to store notification settings for admins"""

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, 
        editable=False, unique=True)
    notification = models.ForeignKey(Notifications, on_delete=models.RESTRICT)
    admin = models.ForeignKey(User, on_delete=models.RESTRICT)
    email_alerts = models.BooleanField(default=False)
    app_alerts = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification for {self.admin_id}"


class NotificationEvent(models.Model):
    """Persistent inbox entry paired with the user's real-time notification."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notification_events")
    title = models.CharField(max_length=255)
    message = models.TextField()
    category = models.CharField(max_length=64, default="GENERAL")
    payload = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "is_read", "-created_at"],
                name="notificatio_user_id_c2cdbc_idx",
            )
        ]
