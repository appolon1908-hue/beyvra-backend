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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification for {self.user.email}: {self.name}"


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