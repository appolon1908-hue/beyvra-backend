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
