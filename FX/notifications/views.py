import hashlib
import hmac
import json
from django.conf import settings
from django.http import Http404
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from integrations.throttles import WebhookRetryThrottle, WebhookTestThrottle
from integrations.permissions import organization_for_request

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


class UpdateNotifications(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    serializer_class = UserNotificationSerializer

    def put(self, request):
        notification_id = request.data.get("notification_id")

        if not notification_id:
            return Response({"error": "Notification ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            notification = Notifications.objects.get(id=notification_id)
        except Notifications.DoesNotExist:
            return Response({"error": "Notification does not exist"}, status=status.HTTP_404_NOT_FOUND)

        try:
            user_notification = UserNotifications.objects.get(user=request.user, notification=notification, organization=organization_for_request(request))
            user_notification.is_enabled = request.data.get("is_enabled", False)
            user_notification.save()
        except UserNotifications.DoesNotExist:
            user_notification = UserNotifications.objects.create(
                user=request.user,
                organization=organization_for_request(request),
                notification=notification,
                is_enabled=request.data.get("is_enabled", True),
            )

        serializer = self.get_serializer(user_notification)
        return Response(serializer.data, status=status.HTTP_200_OK)


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

    def post(self, request):
        # Create a new alert for the user
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user, organization=organization_for_request(request))
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserAlertDetail(generics.GenericAPIView):
    """Get a particular alert by ID"""

    serializer_class = PriceAlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserAlerts.objects.filter(user=self.request.user)

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

    def post(self, request, event_id):
        event = generics.get_object_or_404(NotificationEvent, id=event_id, user=request.user)
        event.is_read = True
        event.save(update_fields=["is_read"])
        return Response(NotificationEventSerializer(event).data)


class NotificationReadAll(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = NotificationEvent.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"updated": updated})


class StagingWebhookReceiver(generics.GenericAPIView):
    """Controlled staging sink for verifying Codestra webhook signatures."""

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

    def perform_create(self, serializer):
        secret = serializer.validated_data.pop("secret", None)
        if not secret:
            raise ValueError("secret required")
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
    def test(self, request, pk=None):
        from django.db import transaction
        from .services import _queue_webhook, emit_notification
        subscription = self.get_object()
        event = emit_notification(user_id=request.user.id, title="Webhook test", message="Codestra webhook delivery test.", category="WEBHOOK_TEST", payload={"subscription_id": str(subscription.id)}, force=True)
        delivery, _ = WebhookDelivery.objects.get_or_create(subscription=subscription, event=event)
        transaction.on_commit(lambda delivery_id=delivery.id: _queue_webhook(delivery_id))
        return Response(NotificationEventSerializer(event).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], throttle_classes=[WebhookRetryThrottle])
    def retry(self, request, pk=None):
        """Retry only a failed/dead-letter delivery owned by this user."""
        delivery = WebhookDelivery.objects.filter(subscription=self.get_object(), id=request.data.get("delivery_id"), status__in=["F", "D"]).first()
        if not delivery:
            return Response({"detail": "failed delivery not found"}, status=status.HTTP_404_NOT_FOUND)
        delivery.status = "P"; delivery.last_error = ""; delivery.save(update_fields=["status", "last_error", "updated_at"])
        from .services import _queue_webhook
        _queue_webhook(delivery.id)
        return Response({"delivery_id": str(delivery.id), "status": delivery.status}, status=status.HTTP_202_ACCEPTED)
