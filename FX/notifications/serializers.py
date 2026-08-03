import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings
from rest_framework import serializers

from .models import *


class UserNotificationSerializer(serializers.ModelSerializer):
    """User Notification serializer"""

    notification_id = serializers.UUIDField(required=True)

    class Meta:
        model = UserNotifications
        fields = ["notification_id", "is_enabled"]


class NotificationSerializer(serializers.ModelSerializer):
    """Notification Serializer"""

    class Meta:
        model = Notifications
        fields = "__all__"


class PriceAlertSerializer(serializers.ModelSerializer):
    """Price Alert Serializer"""

    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = UserAlerts
        exclude = ("user",)


class NotificationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationEvent
        fields = ["id", "title", "message", "category", "payload", "is_read", "created_at"]
        read_only_fields = fields


class WebhookSubscriptionSerializer(serializers.ModelSerializer):
    secret = serializers.CharField(write_only=True, min_length=16)

    class Meta:
        model = WebhookSubscription
        fields = ["id", "url", "secret", "categories", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_url(self, value):
        parsed = urlparse(value)
        if parsed.scheme != "https" and not settings.DEBUG:
            raise serializers.ValidationError("Webhook URLs must use HTTPS.")
        try:
            addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        except socket.gaierror as exc:
            raise serializers.ValidationError("Webhook hostname could not be resolved.") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not settings.DEBUG and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
                raise serializers.ValidationError("Webhook URLs cannot target private network addresses.")
        return value

    def validate_categories(self, value):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("Categories must be a list of strings.")
        return value


class WebhookDeliverySerializer(serializers.ModelSerializer):
    event = NotificationEventSerializer(read_only=True)

    class Meta:
        model = WebhookDelivery
        fields = ["id", "event", "status", "attempts", "response_code", "last_error", "delivered_at", "created_at"]
        read_only_fields = fields
