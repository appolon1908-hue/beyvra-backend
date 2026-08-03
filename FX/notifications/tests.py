from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from datetime import timedelta
import hashlib
import hmac
import json
import requests
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from notifications.models import Notifications, NotificationEvent, UserNotifications, WebhookDelivery, WebhookSubscription
from notifications.services import emit_notification
from notifications.tasks import deliver_webhook, purge_expired_notifications


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

    @patch("notifications.tasks.requests.post")
    def test_webhook_delivery_posts_signed_json_and_records_success(self, post):
        response = post.return_value
        response.status_code = 202
        response.raise_for_status.return_value = None
        subscription = WebhookSubscription.objects.create(
            user=self.user, url="https://example.com/events", secret="a-secure-test-secret"
        )
        event = NotificationEvent.objects.create(
            user=self.user, title="Deposit approved", message="Funds are ready", category="DEPOSIT",
            payload={"amount": "10.00"},
        )
        delivery = WebhookDelivery.objects.create(subscription=subscription, event=event)

        deliver_webhook.run(str(delivery.id))

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "S")
        self.assertEqual(delivery.attempts, 1)
        self.assertEqual(delivery.response_code, 202)
        headers = post.call_args.kwargs["headers"]
        self.assertTrue(headers["X-Codestra-Signature-256"].startswith("sha256="))
        self.assertEqual(post.call_args.kwargs["json"] if "json" in post.call_args.kwargs else None, None)
        self.assertIn(b'"type":"DEPOSIT"', post.call_args.kwargs["data"])

    def test_webhook_update_keeps_secret_when_omitted(self):
        with patch("notifications.serializers.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
            created = self.client.post(
                "/api/notification/webhooks/",
                {"url": "https://example.com/events", "secret": "a-secure-test-secret", "categories": ["TRADE"]},
                format="json", secure=True,
            )
            webhook_id = created.data["id"]
            updated = self.client.patch(
                f"/api/notification/webhooks/{webhook_id}/",
                {"categories": ["DEPOSIT"]}, format="json", secure=True,
            )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data["categories"], ["DEPOSIT"])
        self.assertEqual(WebhookSubscription.objects.get(pk=webhook_id).secret, "a-secure-test-secret")

    @override_settings(STAGING_WEBHOOK_RECEIVER_ENABLED=True, STAGING_WEBHOOK_RECEIVER_SECRET="receiver-secret")
    def test_staging_receiver_verifies_signature_and_supports_controlled_failure(self):
        body = json.dumps({"id": "event-1", "type": "TRADE"}, separators=(",", ":")).encode()
        signature = "sha256=" + hmac.new(b"receiver-secret", body, hashlib.sha256).hexdigest()
        accepted = self.client.post(
            "/api/notification/staging-receiver/", body,
            content_type="application/json", HTTP_X_CODESTRA_SIGNATURE_256=signature,
            secure=True,
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        rejected = self.client.post(
            "/api/notification/staging-receiver/", body,
            content_type="application/json", HTTP_X_CODESTRA_SIGNATURE_256="sha256=bad",
            secure=True,
        )
        self.assertEqual(rejected.status_code, status.HTTP_401_UNAUTHORIZED)
        failed = self.client.post(
            "/api/notification/staging-receiver/?status=500", body,
            content_type="application/json", HTTP_X_CODESTRA_SIGNATURE_256=signature,
            secure=True,
        )
        self.assertEqual(failed.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @patch("notifications.tasks.requests.post", side_effect=requests.Timeout("receiver timeout"))
    def test_webhook_delivery_records_failure_before_celery_retry(self, post):
        subscription = WebhookSubscription.objects.create(
            user=self.user, url="https://example.com/events", secret="a-secure-test-secret"
        )
        event = NotificationEvent.objects.create(user=self.user, title="Trade", message="Failed", category="TRADE")
        delivery = WebhookDelivery.objects.create(subscription=subscription, event=event)
        with self.assertRaises(requests.Timeout):
            deliver_webhook.run(str(delivery.id))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "F")
        self.assertEqual(delivery.attempts, 1)
        self.assertIn("receiver timeout", delivery.last_error)

    @override_settings(NOTIFICATION_RETENTION_DAYS=30)
    def test_retention_task_removes_only_expired_events(self):
        expired = NotificationEvent.objects.create(
            user=self.user, title="Expired", message="Old event"
        )
        NotificationEvent.objects.filter(pk=expired.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        current = NotificationEvent.objects.create(
            user=self.user, title="Current", message="Keep event"
        )

        deleted = purge_expired_notifications()

        self.assertGreaterEqual(deleted, 1)
        self.assertFalse(NotificationEvent.objects.filter(pk=expired.pk).exists())
        self.assertTrue(NotificationEvent.objects.filter(pk=current.pk).exists())
