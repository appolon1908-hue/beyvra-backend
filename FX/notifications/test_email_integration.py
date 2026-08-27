from unittest.mock import Mock, patch
import uuid

import requests
from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase, override_settings

from notifications.email_client import EmailMiddlewareClient, EmailMiddlewareError
from notifications.models import EmailNotificationPreference
from notifications.services import emit_email_notification
from users.email_verification import queue_email
from users.tasks import process_transactional_email_outbox


class EmailIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="email-test@example.test", password="test", phone_number="+12025550198")

    def test_emit_is_deterministic_and_transactional(self):
        event = str(uuid.uuid4())
        item = emit_email_notification(event_type="trading.order_received", user=self.user, event_id=event,
                                       correlation_id=uuid.uuid4(), template_id="order_received",
                                       template_parameters={"action": "Order received. Review it in Beyvra."})
        self.assertEqual(item.idempotency_key, f"trading.order_received:{event}")
        self.assertEqual(item.tenant_id, "beyvra")
        self.assertEqual(item.status, "pending")

    def test_optional_preference_suppresses_but_security_is_mandatory(self):
        EmailNotificationPreference.objects.create(user=self.user, trading=False)
        self.assertIsNone(emit_email_notification(event_type="trading.order_received", user=self.user, event_id="order-1",
                                                  correlation_id=uuid.uuid4(), template_id="order_received", template_parameters={"action": "x"}))
        security = emit_email_notification(event_type="security.new_login", user=self.user, event_id="login-1",
                                           correlation_id=uuid.uuid4(), template_id="new_login", template_parameters={"action": "x"})
        self.assertIsNotNone(security)

    @override_settings(TRANSACTIONAL_EMAIL_ENABLED=True)
    @patch("notifications.email_client.EmailMiddlewareClient.submit")
    def test_success_and_duplicate_safe_submission(self, submit):
        submit.return_value = {"notification_id": "provider-notification", "status": "QUEUED", "duplicate": False}
        item = emit_email_notification(event_type="security.new_login", user=self.user, event_id="login-2",
                                       correlation_id=uuid.uuid4(), template_id="new_login", template_parameters={"action": "x"})
        self.assertEqual(process_transactional_email_outbox.run(), "sent")
        item.refresh_from_db()
        self.assertEqual((item.status, item.provider_status), ("sent", "QUEUED"))

    @override_settings(TRANSACTIONAL_EMAIL_ENABLED=True)
    @patch("notifications.email_client.EmailMiddlewareClient.submit", side_effect=EmailMiddlewareError("NETWORK_FAILURE", True))
    def test_timeout_does_not_change_business_state_and_retries(self, submit):
        item = emit_email_notification(event_type="funds.withdrawal_completed", user=self.user, event_id="withdrawal-1",
                                       correlation_id=uuid.uuid4(), template_id="withdrawal_completed", template_parameters={"action": "x"})
        self.assertEqual(process_transactional_email_outbox.run(), "failed")
        item.refresh_from_db()
        self.assertEqual(item.status, "pending")
        self.assertEqual(item.last_error_code, "NETWORK_FAILURE")

    @patch("notifications.email_client.requests.post", side_effect=requests.Timeout())
    def test_token_timeout_is_classified_without_secret_logging(self, post):
        with patch.object(EmailMiddlewareClient, "_credential", return_value="not-logged"):
            with self.assertRaises(EmailMiddlewareError) as raised:
                EmailMiddlewareClient().token()
        self.assertEqual(raised.exception.error_class, "AUTHENTICATION_FAILURE")

    @override_settings(TRANSACTIONAL_EMAIL_ENABLED=True)
    @patch("notifications.email_client.EmailMiddlewareClient.submit")
    def test_non_otp_template_preserves_queued_parameters(self, submit):
        submit.return_value = {"notification_id": "provider-notification", "status": "QUEUED"}
        parameters = {"action": "Use the one-time reset link.", "reset_path": "/reset/opaque"}
        emit_email_notification(
            event_type="account.password_reset_requested",
            user=self.user,
            event_id="password-reset-1",
            correlation_id=uuid.uuid4(),
            template_id="password_reset",
            template_parameters=parameters,
        )
        self.assertEqual(process_transactional_email_outbox.run(), "sent")
        self.assertEqual(submit.call_args.args[1], parameters)

    def test_duplicate_email_intent_returns_existing_row(self):
        kwargs = {
            "event_type": "funds.deposit_completed",
            "email": self.user.email,
            "template_key": "deposit_completed",
            "payload": {"action": "Deposit approved."},
            "idempotency_key": "funds.deposit_completed:payment-1",
            "user_id": self.user.pk,
        }
        first = queue_email(**kwargs)
        second = queue_email(**kwargs)
        self.assertEqual(first.pk, second.pk)

    def test_email_outbox_has_durable_periodic_recovery(self):
        self.assertEqual(
            settings.CELERY_BEAT_SCHEDULE["process_transactional_email_outbox"]["task"],
            "users.tasks.process_transactional_email_outbox",
        )

    @patch("notifications.email_client.requests.post")
    def test_oauth_token_cache_is_shared_between_client_instances(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"access_token": "cached-token", "expires_in": 300}
        post.return_value = response
        EmailMiddlewareClient._token = ""
        EmailMiddlewareClient._expires_at = 0.0
        with patch.object(EmailMiddlewareClient, "_credential", return_value="secret"):
            self.assertEqual(EmailMiddlewareClient().token(), "cached-token")
            self.assertEqual(EmailMiddlewareClient().token(), "cached-token")
        self.assertEqual(post.call_count, 1)

