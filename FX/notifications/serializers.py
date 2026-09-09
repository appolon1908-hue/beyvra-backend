import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings
from rest_framework import serializers

from .models import *


class EmailNotificationPreferenceSerializer(serializers.ModelSerializer):
    account = serializers.SerializerMethodField()
    security = serializers.SerializerMethodField()

    class Meta:
        model = EmailNotificationPreference
        fields = ("account", "security", "trading", "funds", "statements", "support", "marketing", "updated_at")
        read_only_fields = ("account", "security", "marketing", "updated_at")

    def get_account(self, obj):
        return True

    def get_security(self, obj):
        return True


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
        exclude = ("user", "organization")


class NotificationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationEvent
        fields = ["id", "title", "message", "category", "payload", "is_read", "created_at"]
        read_only_fields = fields


class WebhookSubscriptionSerializer(serializers.ModelSerializer):
    secret = serializers.CharField(write_only=True, min_length=16, required=False)

    class Meta:
        model = WebhookSubscription
        fields = ["id", "url", "secret", "categories", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        if self.instance is None and not attrs.get("secret"):
            raise serializers.ValidationError({"secret": "This field is required when creating a webhook."})
        return attrs

    def update(self, instance, validated_data):
        # Secrets are write-only; omitting one keeps the current signing key.
        validated_data.pop("secret", None)
        return super().update(instance, validated_data)

    def validate_url(self, value):
        try:
            parsed = urlparse(value)
            port = parsed.port
            if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                    or parsed.fragment or "%" in parsed.hostname
                    or parsed.scheme not in {"http", "https"}
                    or any(ord(char) <= 32 for char in value)):
                raise ValueError("invalid webhook authority")
        except ValueError as exc:
            raise serializers.ValidationError("Webhook URL is invalid.") from exc
        if parsed.scheme != "https" and not settings.DEBUG:
            raise serializers.ValidationError("Webhook URLs must use HTTPS.")
        try:
            addresses = socket.getaddrinfo(parsed.hostname, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            if not addresses:
                raise ValueError("empty DNS answer")
            for address in addresses:
                ip = ipaddress.ip_address(address[4][0])
                if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
                    ip = ip.ipv4_mapped
                if not settings.DEBUG and (not ip.is_global or ip.is_multicast or ip.is_reserved):
                    raise serializers.ValidationError("Webhook URLs must target public unicast addresses.")
        except (socket.gaierror, ValueError) as exc:
            raise serializers.ValidationError("Webhook hostname could not be resolved safely.") from exc
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
