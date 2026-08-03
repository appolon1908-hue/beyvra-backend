from django.http import Http404
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import *
from .serializers import *


class NotificationListing(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return Notifications.objects.all()

    def get(self, request):
        user = request.user
        notifications = self.get_queryset()
        user_notifications = UserNotifications.objects.filter(user=user)
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
            user_notification = UserNotifications.objects.get(user=request.user, notification=notification)
            user_notification.is_enabled = request.data.get("is_enabled", False)
            user_notification.save()
        except UserNotifications.DoesNotExist:
            user_notification = UserNotifications.objects.create(
                user=request.user,
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
        return UserAlerts.objects.filter(user=self.request.user)

    def get(self, request):
        # Get all alerts for the authenticated user
        user_alerts = self.get_queryset()
        serializer = self.serializer_class(user_alerts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        # Create a new alert for the user
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)  # Assign the authenticated user to the alert
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


class WebhookSubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = WebhookSubscriptionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return WebhookSubscription.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"])
    def deliveries(self, request, pk=None):
        subscription = self.get_object()
        queryset = subscription.deliveries.select_related("event")
        page = self.paginate_queryset(queryset)
        serializer = WebhookDeliverySerializer(page or queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        from .services import emit_notification
        event = emit_notification(
            user_id=request.user.id,
            title="Webhook test",
            message="Codestra webhook delivery test.",
            category="WEBHOOK_TEST",
            payload={"subscription_id": str(self.get_object().id)},
            force=True,
        )
        return Response(NotificationEventSerializer(event).data, status=status.HTTP_202_ACCEPTED)
