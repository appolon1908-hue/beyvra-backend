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
from django.db import transaction
from django.utils import timezone
from notifications.models import EmailNotificationPreference, Notifications, NotificationEvent, UserNotifications, WebhookDelivery, WebhookSubscription
from notifications.services import emit_notification
from notifications.tasks import deliver_webhook, purge_expired_notifications
from integrations.models import Organization, OrganizationMembership


class NotificationInboxTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="inbox@example.com", password="test-pass", phone_number="+12025550133"
        )
        self.other = get_user_model().objects.create_user(
            email="other-inbox@example.com", password="test-pass", phone_number="+12025550134"
        )
        self.organization = Organization.objects.create(name="Notification test tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.organization, role="member")
        OrganizationMembership.objects.create(user=self.other, organization=self.organization, role="member")
        NotificationEvent.objects.all().delete()
        self.event = NotificationEvent.objects.create(
            user=self.user, organization=self.organization, title="Trade placed", message="Your demo trade is open", category="TRADE"
        )
        NotificationEvent.objects.create(
            user=self.other, organization=self.organization, title="Private", message="Not visible to first user"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.command_number = 0

    def command_headers(self, *, version=None):
        self.command_number += 1
        headers = {
            "HTTP_IDEMPOTENCY_KEY": f"notification-command-{self.command_number}",
            "HTTP_X_REQUEST_ID": f"65cbf766-67ac-4f77-868a-{self.command_number:012d}",
        }
        if version is not None:
            headers["HTTP_IF_MATCH"] = version
        return headers

    def test_inbox_is_user_scoped_and_can_mark_read(self):
        response = self.client.get("/api/notification/inbox/", secure=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertEqual(len(results), 1)

        read = self.client.post(
            f"/api/notification/inbox/{self.event.id}/read/", secure=True, **self.command_headers()
        )
        self.assertEqual(read.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_read)

    def test_mark_all_read(self):
        NotificationEvent.objects.create(user=self.user, organization=self.organization, title="Second", message="Another event")
        response = self.client.post("/api/notification/inbox/read-all/", secure=True, **self.command_headers())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["updated"], 2)

    def test_legacy_null_organization_events_remain_readable(self):
        legacy = NotificationEvent.objects.create(user=self.user, organization=None, title="Legacy", message="Before tenancy")
        read = self.client.post(f"/api/notification/inbox/{legacy.id}/read/", secure=True, **self.command_headers())
        self.assertEqual(read.status_code, status.HTTP_200_OK)
        legacy.refresh_from_db(); self.assertTrue(legacy.is_read)

    def test_inbox_is_paginated(self):
        for number in range(12):
            NotificationEvent.objects.create(user=self.user, title=f"Event {number}", message="Update")
        response = self.client.get("/api/notification/inbox/", secure=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["next"])

    def test_disabled_push_preference_suppresses_event(self):
        preference = Notifications.objects.create(name="Push Notifications")
        UserNotifications.objects.create(user=self.user, organization=self.organization, notification=preference, is_enabled=False)
        event = emit_notification(
            user_id=self.user.id, title="Deposit completed", message="Done", category="DEPOSIT"
        )
        self.assertIsNone(event)

    @patch("notifications.services._queue_webhook")
    def test_event_creates_matching_webhook_delivery(self, queue_webhook):
        subscription = WebhookSubscription.objects.create(
            user=self.user,
            organization=self.organization,
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

    @patch("notifications.services._queue_webhook")
    def test_webhook_queue_is_deferred_until_transaction_commit(self, queue_webhook):
        WebhookSubscription.objects.create(
            user=self.user,
            organization=self.organization,
            url="https://example.com/commit-boundary",
            secret="a-secure-test-secret",
            categories=["TRADE"],
        )
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                emit_notification(user_id=self.user.id, title="Trade", message="Done", category="TRADE")
        queue_webhook.assert_called_once()

    def test_webhook_api_is_user_scoped_and_secret_is_write_only(self):
        headers = self.command_headers()
        with patch("notifications.serializers.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
            response = self.client.post(
                "/api/notification/webhooks/",
                {"url": "https://example.com/events", "secret": "a-secure-test-secret", "categories": ["TRADE"]},
                format="json", secure=True, **headers,
            )
            replay = self.client.post(
                "/api/notification/webhooks/",
                {"url": "https://example.com/events", "secret": "a-secure-test-secret", "categories": ["TRADE"]},
                format="json", secure=True, **headers,
            )
            conflict = self.client.post(
                "/api/notification/webhooks/",
                {"url": "https://example.com/changed", "secret": "a-secure-test-secret", "categories": ["TRADE"]},
                format="json", secure=True, **headers,
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(replay.status_code, status.HTTP_201_CREATED)
        self.assertEqual(replay.data, response.data)
        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT)
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
        self.assertEqual(headers["X-Codestra-Signature-Version"], "HMAC-SHA256")
        self.assertEqual(headers["X-Codestra-Event-Id"], str(event.id))
        self.assertEqual(post.call_args.kwargs["json"] if "json" in post.call_args.kwargs else None, None)
        self.assertIn(b'"type":"DEPOSIT"', post.call_args.kwargs["data"])

    def test_webhook_update_keeps_secret_when_omitted(self):
        with patch("notifications.serializers.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
            created = self.client.post(
                "/api/notification/webhooks/",
                {"url": "https://example.com/events", "secret": "a-secure-test-secret", "categories": ["TRADE"]},
                format="json", secure=True, **self.command_headers(),
            )
            webhook_id = created.data["id"]
            updated = self.client.patch(
                f"/api/notification/webhooks/{webhook_id}/",
                {"categories": ["DEPOSIT"]}, format="json", secure=True,
                **self.command_headers(version=created.data["updated_at"]),
            )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data["categories"], ["DEPOSIT"])
        stored = WebhookSubscription.objects.get(pk=webhook_id)
        self.assertIsNone(stored.secret)
        self.assertTrue(stored.secret_ciphertext)

    def test_email_preference_and_webhook_delete_replay_after_mutation(self):
        preference = EmailNotificationPreference.objects.create(user=self.user, organization=self.organization)
        version = preference.updated_at.isoformat().replace("+00:00", "Z")
        headers = self.command_headers(version=version)
        first = self.client.patch("/api/notification/email-preferences/", {"trading": False}, format="json", secure=True, **headers)
        replay = self.client.patch("/api/notification/email-preferences/", {"trading": False}, format="json", secure=True, **headers)
        self.assertEqual(first.status_code, 200); self.assertEqual(replay.data, first.data)

        subscription = WebhookSubscription.objects.create(user=self.user, organization=self.organization, url="https://example.com/delete", secret="test-secret")
        delete_headers = self.command_headers(version=subscription.updated_at.isoformat().replace("+00:00", "Z"))
        first_delete = self.client.delete(f"/api/notification/webhooks/{subscription.id}/", secure=True, **delete_headers)
        replay_delete = self.client.delete(f"/api/notification/webhooks/{subscription.id}/", secure=True, **delete_headers)
        self.assertEqual(first_delete.status_code, 204); self.assertEqual(replay_delete.status_code, 204)

    def test_missing_webhook_update_is_404_and_delivery_retry_replays(self):
        missing = self.client.patch(
            "/api/notification/webhooks/00000000-0000-0000-0000-000000000001/", {}, format="json", secure=True,
            **self.command_headers(version="missing"),
        )
        self.assertEqual(missing.status_code, 404)
        subscription = WebhookSubscription.objects.create(user=self.user, organization=self.organization, url="https://example.com/retry", secret="test-secret")
        event = NotificationEvent.objects.create(user=self.user, organization=self.organization, title="Retry", message="Failed")
        delivery = WebhookDelivery.objects.create(subscription=subscription, event=event, status="F", attempts=1)
        headers = self.command_headers(version="F:1")
        with patch("notifications.services._queue_webhook"):
            with self.captureOnCommitCallbacks(execute=True):
                first = self.client.post(f"/api/notification/webhooks/{subscription.id}/retry/", {"delivery_id": str(delivery.id)}, format="json", secure=True, **headers)
            replay = self.client.post(f"/api/notification/webhooks/{subscription.id}/retry/", {"delivery_id": str(delivery.id)}, format="json", secure=True, **headers)
        self.assertEqual(first.status_code, 202); self.assertEqual(replay.data, first.data)

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
