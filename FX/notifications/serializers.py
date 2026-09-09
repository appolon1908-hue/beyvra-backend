from rest_framework import serializers

from .models import *
from .webhook_transport import resolve_destination, UnsafeWebhookDestination


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
            resolve_destination(value)
        except UnsafeWebhookDestination as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def validate_categories(self, value):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("Categories must be a list of strings.")
        return value


class WebhookDeliverySerializer(serializers.ModelSerializer):
    event = NotificationEventSerializer(read_only=True)

    class Meta:
        model = WebhookDelivery
        fields = ["id", "event", "status", "attempts", "attempt_limit", "response_code", "last_error", "delivered_at", "created_at"]
        read_only_fields = fields


class WebhookDeliveryIdField(serializers.UUIDField):
    def to_internal_value(self, data):
        # DRF also accepts integers (including booleans) as UUIDs; the wire
        # contract requires a UUID string rather than numeric coercion.
        if not isinstance(data, str):
            self.fail("invalid", value=data)
        return super().to_internal_value(data)


class WebhookRetrySerializer(serializers.Serializer):
    delivery_id = WebhookDeliveryIdField(required=True)
