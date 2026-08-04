import uuid

from django.db import models
from users.models import User
from integrations.models import Organization


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
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="user_notifications")
    is_enabled = models.BooleanField(default=True)
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
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="user_alerts")
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
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="notification_events")
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


class WebhookSubscription(models.Model):
    """User-owned endpoint for signed notification event delivery."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notification_webhooks")
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE, related_name="notification_webhooks")
    url = models.URLField(max_length=500)
    # Legacy field is retained only for expand/contract migration compatibility;
    # new writes use authenticated encryption fields below.
    secret = models.CharField(max_length=255, null=True, blank=True)
    secret_ciphertext = models.TextField(null=True, blank=True)
    secret_nonce = models.CharField(max_length=64, null=True, blank=True)
    secret_key_version = models.CharField(max_length=32, default="v1")
    secret_fingerprint = models.CharField(max_length=16, default="")
    secret_created_at = models.DateTimeField(null=True, blank=True)
    secret_rotated_at = models.DateTimeField(null=True, blank=True)
    secret_revoked_at = models.DateTimeField(null=True, blank=True)
    categories = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "url"], name="unique_user_webhook_url"),
            models.UniqueConstraint(fields=["organization", "url"], name="unique_org_webhook_url"),
        ]


class WebhookDelivery(models.Model):
    STATUS_CHOICES = (("P", "Pending"), ("S", "Successful"), ("F", "Failed"), ("D", "Dead letter"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(WebhookSubscription, on_delete=models.CASCADE, related_name="deliveries")
    event = models.ForeignKey(NotificationEvent, on_delete=models.CASCADE, related_name="webhook_deliveries")
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default="P")
    attempts = models.PositiveSmallIntegerField(default=0)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["subscription", "event"], name="unique_webhook_event_delivery")
        ]
