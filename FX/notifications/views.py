import hashlib
import hmac
import json
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from integrations.throttles import WebhookRetryThrottle, WebhookTestThrottle
from integrations.permissions import organization_for_request
from .commands import COMMAND_PARAMETERS, VERSIONED_COMMAND_PARAMETERS, begin, complete, context

from .models import *
from .serializers import *


class NotificationListing(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return Notifications.objects.all()

    def get(self, request):
        user = request.user
        notifications = self.get_queryset()
        organization = organization_for_request(request)
        user_notifications = UserNotifications.objects.filter(user=user, organization=organization)
        user_notification_dict = {data.notification_id: data.is_enabled for data in user_notifications}

        notifications_data = []
        for notification in notifications:
            is_enabled = user_notification_dict.get(notification.id, True)
            notification_data = NotificationSerializer(notification).data
            notification_data["is_enabled"] = is_enabled
            notifications_data.append(notification_data)

        return Response({"notifications": notifications_data}, status=status.HTTP_200_OK)


class EmailNotificationPreferences(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmailNotificationPreferenceSerializer

    def get_object(self):
        value, _ = EmailNotificationPreference.objects.get_or_create(
            user=self.request.user, defaults={"organization": organization_for_request(self.request)}
        )
        return value

    def get(self, request):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def patch(self, request):
        command, error = context(request, require_version=True)
        if error: return error
        key, _, correlation_id, expected_version = command
        organization = organization_for_request(request)
        instance = EmailNotificationPreference.objects.select_for_update().filter(user=request.user).first()
        serializer = self.serializer_class(instance or self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        record, replay = begin(request, organization=organization, key=key, payload={"expected_version": expected_version, **serializer.validated_data})
        if replay: return replay
        if instance and expected_version != instance.updated_at.isoformat().replace("+00:00", "Z"):
            record.delete(); return Response({"detail": "VERSION_CONFLICT"}, status=409)
        serializer.save(marketing=False)
        body = complete(record, request=request, organization=organization, correlation_id=correlation_id, action="notification.email_preference.update", status=200, body=serializer.data, resource_type="email_notification_preference", resource_id=serializer.instance.pk)
        return Response(body)


class UpdateNotifications(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    serializer_class = UserNotificationSerializer

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def put(self, request):
        notification_id = request.data.get("notification_id")

        if not notification_id:
            return Response({"error": "Notification ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            notification = Notifications.objects.get(id=notification_id)
        except Notifications.DoesNotExist:
            return Response({"error": "Notification does not exist"}, status=status.HTTP_404_NOT_FOUND)

        organization = organization_for_request(request)
        command, error = context(request)
        if error: return error
        key, _, correlation_id, _ = command
        desired = bool(request.data.get("is_enabled", False))
        record, replay = begin(request, organization=organization, key=key, payload={"notification_id": str(notification.id), "is_enabled": desired})
        if replay: return replay
        try:
            user_notification = UserNotifications.objects.select_for_update().get(user=request.user, notification=notification, organization=organization)
            user_notification.is_enabled = request.data.get("is_enabled", False)
            user_notification.save()
        except UserNotifications.DoesNotExist:
            user_notification = UserNotifications.objects.create(
                user=request.user,
                organization=organization,
                notification=notification,
                is_enabled=request.data.get("is_enabled", True),
            )

        serializer = self.get_serializer(user_notification)
        body = complete(record, request=request, organization=organization, correlation_id=correlation_id, action="notification.preference.update", status=200, body=serializer.data, resource_type="notification_preference", resource_id=user_notification.pk)
        return Response(body, status=status.HTTP_200_OK)


class UserAlertsListing(generics.GenericAPIView):
    """Get all alerts for the authenticated user"""

    serializer_class = PriceAlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserAlerts.objects.filter(user=self.request.user, organization=organization_for_request(self.request))

    def get(self, request):
        # Get all alerts for the authenticated user
        user_alerts = self.get_queryset()
        serializer = self.serializer_class(user_alerts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        # Create a new alert for the user
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = organization_for_request(request); command, error = context(request)
        if error: return error
        key, _, correlation_id, _ = command
        record, replay = begin(request, organization=organization, key=key, payload=serializer.validated_data)
        if replay: return replay
        serializer.save(user=request.user, organization=organization)
        body = complete(record, request=request, organization=organization, correlation_id=correlation_id, action="notification.price_alert.create", status=201, body=serializer.data, resource_type="price_alert", resource_id=serializer.instance.pk)
        return Response(body, status=status.HTTP_201_CREATED)


class UserAlertDetail(generics.GenericAPIView):
    """Get a particular alert by ID"""

    serializer_class = PriceAlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserAlerts.objects.filter(user=self.request.user, organization=organization_for_request(self.request))

    def get_object(self, alert_id):
        try:
            return self.get_queryset().get(id=alert_id)
        except UserAlerts.DoesNotExist:
            raise Http404

    def get(self, request, alert_id):
        # Get a particular alert by ID
        try:
            user_alert = self.get_object(alert_id)
            if user_alert.user != request.user:
                return Response({"error": "Alert not found"}, status=status.HTTP_404_NOT_FOUND)
            serializer = self.serializer_class(user_alert)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Http404:
            return Response({"error": "Alert not found"}, status=status.HTTP_404_NOT_FOUND)


class NotificationInbox(generics.ListAPIView):
    serializer_class = NotificationEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return NotificationEvent.objects.filter(user=self.request.user)


class NotificationEventRead(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request, event_id):
        organization = organization_for_request(request); command, error = context(request)
        if error: return error
        key, _, correlation_id, _ = command
        event = generics.get_object_or_404(
            NotificationEvent.objects.select_for_update().filter(Q(organization=organization) | Q(organization__isnull=True)),
            id=event_id, user=request.user,
        )
        record, replay = begin(request, organization=organization, key=key, payload={"event_id": str(event_id), "action": "read"})
        if replay: return replay
        event.is_read = True
        event.save(update_fields=["is_read"])
        body = complete(record, request=request, organization=organization, correlation_id=correlation_id, action="notification.inbox.read", status=200, body=NotificationEventSerializer(event).data, resource_type="notification_event", resource_id=event.pk)
        return Response(body)


class NotificationReadAll(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        organization = organization_for_request(request); command, error = context(request)
        if error: return error
        key, _, correlation_id, _ = command
        record, replay = begin(request, organization=organization, key=key, payload={"action": "read_all"})
        if replay: return replay
        updated = NotificationEvent.objects.filter(user=request.user, is_read=False).filter(
            Q(organization=organization) | Q(organization__isnull=True)
        ).update(is_read=True)
        body = complete(record, request=request, organization=organization, correlation_id=correlation_id, action="notification.inbox.read_all", status=200, body={"updated": updated}, resource_type="notification_inbox", resource_id=request.user.pk)
        return Response(body)


class StagingWebhookReceiver(generics.GenericAPIView):
    """Controlled staging sink for verifying Beyvra compatibility webhook signatures."""

    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.STAGING_WEBHOOK_RECEIVER_ENABLED:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        signature = request.headers.get("X-Codestra-Signature-256", "")
        expected = "sha256=" + hmac.new(
            settings.STAGING_WEBHOOK_RECEIVER_SECRET.encode(), request.body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return Response({"detail": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return Response({"detail": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)
        if request.query_params.get("status") == "500":
            return Response({"detail": "Controlled receiver failure"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"received": True, "event_id": payload.get("id")}, status=status.HTTP_200_OK)


class WebhookSubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = WebhookSubscriptionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return WebhookSubscription.objects.filter(
            user=self.request.user,
            organization=organization_for_request(self.request),
        )

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data); serializer.is_valid(raise_exception=True)
        organization = organization_for_request(request); command, error = context(request)
        if error: return error
        key, _, correlation_id, _ = command
        record, replay = begin(request, organization=organization, key=key, payload=serializer.validated_data)
        if replay: return replay
        self.perform_create(serializer)
        body = complete(record, request=request, organization=organization, correlation_id=correlation_id, action="notification.webhook.create", status=201, body=serializer.data, resource_type="webhook_subscription", resource_id=serializer.instance.pk)
        return Response(body, status=201)

    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = generics.get_object_or_404(self.get_queryset().select_for_update(), pk=kwargs["pk"])
        serializer = self.get_serializer(instance, data=request.data, partial=partial); serializer.is_valid(raise_exception=True)
        organization = organization_for_request(request); command, error = context(request, require_version=True)
        if error: return error
        key, _, correlation_id, expected_version = command
        current_version = instance.updated_at.isoformat().replace("+00:00", "Z")
        record, replay = begin(request, organization=organization, key=key, payload={"subscription_id": str(instance.pk), "expected_version": expected_version, **serializer.validated_data})
        if replay: return replay
        if expected_version != current_version:
            record.delete(); return Response({"detail": "VERSION_CONFLICT"}, status=409)
        self.perform_update(serializer)
        body = complete(record, request=request, organization=organization, correlation_id=correlation_id, action="notification.webhook.update", status=200, body=serializer.data, resource_type="webhook_subscription", resource_id=instance.pk)
        return Response(body)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        organization = organization_for_request(request); command, error = context(request, require_version=True)
        if error: return error
        key, _, correlation_id, expected_version = command
        record, replay = begin(request, organization=organization, key=key, payload={"subscription_id": str(kwargs["pk"]), "action": "delete", "expected_version": expected_version})
        if replay: return replay
        instance = generics.get_object_or_404(self.get_queryset().select_for_update(), pk=kwargs["pk"])
        if expected_version != instance.updated_at.isoformat().replace("+00:00", "Z"):
            record.delete(); return Response({"detail": "VERSION_CONFLICT"}, status=409)
        resource_id = instance.pk; self.perform_destroy(instance)
        body = complete(record, request=request, organization=organization, correlation_id=correlation_id, action="notification.webhook.delete", status=204, body={}, resource_type="webhook_subscription", resource_id=resource_id)
        return Response(body, status=204)

    def perform_create(self, serializer):
        secret = serializer.validated_data.pop("secret", None)
        if not secret:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"secret": "This field is required when creating a webhook."})
        from .services import encrypted_webhook_fields
        serializer.save(
            user=self.request.user,
            organization=organization_for_request(self.request),
            **encrypted_webhook_fields(secret),
        )

    def perform_update(self, serializer):
        secret = serializer.validated_data.pop("secret", None)
        if secret:
            from .services import encrypted_webhook_fields
            serializer.save(**encrypted_webhook_fields(secret))
        else:
            serializer.save()

    @action(detail=True, methods=["get"])
    def deliveries(self, request, pk=None):
        subscription = self.get_object()
        queryset = subscription.deliveries.select_related("event")
        page = self.paginate_queryset(queryset)
        serializer = WebhookDeliverySerializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], throttle_classes=[WebhookTestThrottle])
    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def test(self, request, pk=None):
        from django.db import transaction
        from .services import _queue_webhook, emit_notification
        subscription = self.get_object()
        organization = organization_for_request(request); command, error = context(request)
        if error: return error
        key, _, correlation_id, _ = command
        record, replay = begin(request, organization=organization, key=key, payload={"subscription_id": str(subscription.pk), "action": "test"})
        if replay: return replay
        event = emit_notification(user_id=request.user.id, title="Webhook test", message="Beyvra webhook delivery test.", category="WEBHOOK_TEST", payload={"subscription_id": str(subscription.id)}, force=True)
        delivery, _ = WebhookDelivery.objects.get_or_create(subscription=subscription, event=event)
        transaction.on_commit(lambda delivery_id=delivery.id: _queue_webhook(delivery_id))
        body = complete(record, request=request, organization=organization, correlation_id=correlation_id, action="notification.webhook.test", status=202, body=NotificationEventSerializer(event).data, resource_type="webhook_test", resource_id=event.pk)
        return Response(body, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], throttle_classes=[WebhookRetryThrottle])
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def retry(self, request, pk=None):
        """Retry only a failed/dead-letter delivery owned by this user."""
        subscription = self.get_object(); organization = organization_for_request(request)
        command, error = context(request, require_version=True)
        if error: return error
        key, _, correlation_id, expected_version = command
        delivery_id = request.data.get("delivery_id")
        record, replay = begin(request, organization=organization, key=key, payload={"subscription_id": str(subscription.pk), "delivery_id": str(delivery_id), "action": "retry", "expected_version": expected_version})
        if replay: return replay
        delivery = WebhookDelivery.objects.select_for_update().filter(subscription=subscription, id=delivery_id, status__in=["F", "D"]).first()
        if not delivery:
            record.delete()
            return Response({"detail": "failed delivery not found"}, status=status.HTTP_404_NOT_FOUND)
        current_version = f"{delivery.status}:{delivery.attempts}"
        if expected_version != current_version:
            record.delete(); return Response({"detail": "VERSION_CONFLICT"}, status=409)
        delivery.status = "P"; delivery.last_error = ""; delivery.save(update_fields=["status", "last_error", "updated_at"])
        from .services import _queue_webhook
        transaction.on_commit(lambda: _queue_webhook(delivery.id))
        body = complete(record, request=request, organization=organization, correlation_id=correlation_id, action="notification.webhook.retry", status=202, body={"delivery_id": str(delivery.id), "status": delivery.status}, resource_type="webhook_delivery", resource_id=delivery.pk)
        return Response(body, status=status.HTTP_202_ACCEPTED)
