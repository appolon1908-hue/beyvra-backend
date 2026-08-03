from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from unittest.mock import patch

from notifications.models import Notifications, NotificationEvent, UserNotifications, WebhookSubscription
from notifications.services import emit_notification


class NotificationInboxTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="inbox@example.com", password="test-pass", phone_number="+12025550133"
        )
        self.other = get_user_model().objects.create_user(
            email="other-inbox@example.com", password="test-pass", phone_number="+12025550134"
        )
        NotificationEvent.objects.all().delete()
        self.event = NotificationEvent.objects.create(
            user=self.user, title="Trade placed", message="Your demo trade is open", category="TRADE"
        )
        NotificationEvent.objects.create(
            user=self.other, title="Private", message="Not visible to first user"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_inbox_is_user_scoped_and_can_mark_read(self):
        response = self.client.get("/api/notification/inbox/", secure=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

        read = self.client.post(
            f"/api/notification/inbox/{self.event.id}/read/", secure=True
        )
        self.assertEqual(read.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_read)

    def test_mark_all_read(self):
        NotificationEvent.objects.create(user=self.user, title="Second", message="Another event")
        response = self.client.post("/api/notification/inbox/read-all/", secure=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated"], 2)

    def test_inbox_is_paginated(self):
        for number in range(12):
            NotificationEvent.objects.create(user=self.user, title=f"Event {number}", message="Update")
        response = self.client.get("/api/notification/inbox/", secure=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["next"])

    def test_disabled_push_preference_suppresses_event(self):
        preference = Notifications.objects.create(name="Push Notifications")
        UserNotifications.objects.create(user=self.user, notification=preference, is_enabled=False)
        event = emit_notification(
            user_id=self.user.id, title="Deposit completed", message="Done", category="DEPOSIT"
        )
        self.assertIsNone(event)

    @patch("notifications.services._queue_webhook")
    def test_event_creates_matching_webhook_delivery(self, queue_webhook):
        subscription = WebhookSubscription.objects.create(
            user=self.user,
            url="https://example.com/codestra-events",
            secret="a-secure-test-secret",
            categories=["TRADE"],
        )
        with self.captureOnCommitCallbacks(execute=True):
            event = emit_notification(
                user_id=self.user.id, title="Trade completed", message="Done", category="TRADE"
            )
        self.assertTrue(subscription.deliveries.filter(event=event).exists())
        queue_webhook.assert_called_once()

    def test_webhook_api_is_user_scoped_and_secret_is_write_only(self):
        with patch("notifications.serializers.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
            response = self.client.post(
                "/api/notification/webhooks/",
                {"url": "https://example.com/events", "secret": "a-secure-test-secret", "categories": ["TRADE"]},
                format="json", secure=True,
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("secret", response.data)
        self.assertEqual(WebhookSubscription.objects.filter(user=self.user).count(), 1)
