from unittest.mock import Mock, patch
import uuid

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from notifications.email_client import EmailMiddlewareClient, EmailMiddlewareError
from notifications.models import EmailNotificationPreference
from notifications.services import emit_email_notification
from users.email_verification import queue_email
from users.tasks import process_transactional_email_outbox


class EmailIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="email-test@example.test",
            password="test",
            phone_number="+12025550198",
        )

    def test_emit_is_deterministic_and_transactional(self):
        event = str(uuid.uuid4())
        item = emit_email_notification(
            event_type="trading.order_received",
            user=self.user,
            event_id=event,
            correlation_id=uuid.uuid4(),
            template_id="order_received",
            template_parameters={"action": "Order received. Review it in Beyvra."},
        )
        self.assertEqual(item.idempotency_key, f"trading.order_received:{event}")
        self.assertEqual(item.tenant_id, "beyvra")
        self.assertEqual(item.status, "pending")

    def test_optional_preference_suppresses_but_security_is_mandatory(self):
        EmailNotificationPreference.objects.create(user=self.user, trading=False)
        self.assertIsNone(
            emit_email_notification(
                event_type="trading.order_received",
                user=self.user,
                event_id="order-1",
                correlation_id=uuid.uuid4(),
                template_id="order_received",
                template_parameters={"action": "x"},
            )
        )
        security = emit_email_notification(
            event_type="security.new_login",
            user=self.user,
            event_id="login-1",
            correlation_id=uuid.uuid4(),
            template_id="new_login",
            template_parameters={"action": "x"},
        )
        self.assertIsNotNone(security)

    @override_settings(TRANSACTIONAL_EMAIL_ENABLED=True)
    @patch("notifications.email_client.EmailMiddlewareClient.submit")
    def test_success_and_duplicate_safe_submission(self, submit):
        submit.return_value = {
            "notification_id": "provider-notification",
            "status": "QUEUED",
            "duplicate": False,
        }
        item = emit_email_notification(
            event_type="security.new_login",
            user=self.user,
            event_id="login-2",
            correlation_id=uuid.uuid4(),
            template_id="new_login",
            template_parameters={"action": "x"},
        )
        self.assertEqual(process_transactional_email_outbox.run(), "sent")
        item.refresh_from_db()
        self.assertEqual((item.status, item.provider_status), ("sent", "QUEUED"))

    @override_settings(TRANSACTIONAL_EMAIL_ENABLED=True)
    @patch(
        "notifications.email_client.EmailMiddlewareClient.submit",
        side_effect=EmailMiddlewareError("NETWORK_FAILURE", True),
    )
    def test_timeout_does_not_change_business_state_and_retries(self, submit):
        item = emit_email_notification(
            event_type="funds.withdrawal_completed",
            user=self.user,
            event_id="withdrawal-1",
            correlation_id=uuid.uuid4(),
            template_id="withdrawal_completed",
            template_parameters={"action": "x"},
        )
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
        submit.return_value = {
            "notification_id": "provider-notification",
            "status": "QUEUED",
        }
        parameters = {
            "action": "Use the one-time reset link.",
            "reset_path": "/reset/opaque",
        }
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

    @patch.dict("os.environ", {"BEYVRA_EMAIL_API_URL": ""})
    def test_missing_middleware_endpoint_keeps_durable_intent_recoverable(self):
        with self.assertRaises(EmailMiddlewareError) as raised:
            EmailMiddlewareClient()._middleware_base_url()
        self.assertEqual(
            raised.exception.error_class, "MIDDLEWARE_ENDPOINT_NOT_CONFIGURED"
        )
        self.assertTrue(raised.exception.retryable)

    @patch.dict(
        "os.environ",
        {"BEYVRA_EMAIL_API_URL": "ftp://middleware.internal/path?token=bad"},
    )
    def test_invalid_middleware_endpoint_fails_closed(self):
        with self.assertRaises(EmailMiddlewareError) as raised:
            EmailMiddlewareClient()._middleware_base_url()
        self.assertEqual(raised.exception.error_class, "MIDDLEWARE_ENDPOINT_INVALID")

    @patch.dict(
        "os.environ", {"BEYVRA_EMAIL_API_URL": "https://api.codestra.co"}
    )
    def test_public_kong_email_route_is_blocked(self):
        with self.assertRaises(EmailMiddlewareError) as raised:
            EmailMiddlewareClient()._middleware_base_url()
        self.assertEqual(
            raised.exception.error_class, "DIRECT_INTEGRATION_BYPASS_BLOCKED"
        )
        self.assertFalse(raised.exception.retryable)

    @patch.dict(
        "os.environ", {"BEYVRA_EMAIL_API_URL": "https://api.codestra.co."}
    )
    def test_public_kong_fqdn_with_terminal_dot_is_blocked(self):
        with self.assertRaises(EmailMiddlewareError) as raised:
            EmailMiddlewareClient()._middleware_base_url()
        self.assertEqual(
            raised.exception.error_class, "DIRECT_INTEGRATION_BYPASS_BLOCKED"
        )

    @patch.dict(
        "os.environ", {"BEYVRA_EMAIL_API_URL": "https://mail.klyrow.com"}
    )
    def test_direct_klyrow_smtp_host_is_blocked_for_business_email(self):
        with self.assertRaises(EmailMiddlewareError) as raised:
            EmailMiddlewareClient()._middleware_base_url()
        self.assertEqual(
            raised.exception.error_class, "DIRECT_INTEGRATION_BYPASS_BLOCKED"
        )

    @patch.dict(
        "os.environ", {"BEYVRA_EMAIL_API_URL": "https://api.klyrow.com"}
    )
    def test_direct_klyrow_api_host_is_blocked_for_business_email(self):
        with self.assertRaises(EmailMiddlewareError) as raised:
            EmailMiddlewareClient()._middleware_base_url()
        self.assertEqual(
            raised.exception.error_class, "DIRECT_INTEGRATION_BYPASS_BLOCKED"
        )

    @override_settings(KEYCLOAK_IDENTITY_ENABLED=True)
    @patch("notifications.email_client.requests.post")
    def test_keycloak_identity_mail_never_enters_business_email_client(self, post):
        item = Mock(template_key="password_reset")
        with self.assertRaises(EmailMiddlewareError) as raised:
            EmailMiddlewareClient().submit(
                item, {"reset_path": "/must-not-leave-keycloak"}
            )
        self.assertEqual(
            raised.exception.error_class, "IDENTITY_MAIL_MUST_USE_KEYCLOAK"
        )
        self.assertFalse(raised.exception.retryable)
        post.assert_not_called()

    @override_settings(KEYCLOAK_IDENTITY_ENABLED=False)
    @patch.dict(
        "os.environ", {"BEYVRA_EMAIL_API_URL": "https://middleware.internal"}
    )
    @patch.object(EmailMiddlewareClient, "token", return_value="service-token")
    @patch("notifications.email_client.requests.post")
    def test_business_mail_uses_only_the_dedicated_middleware_endpoint(
        self, post, token
    ):
        response = Mock(status_code=202)
        response.json.return_value = {"status": "QUEUED"}
        post.return_value = response
        item = Mock(
            template_key="support_case_created",
            notification_id=uuid.uuid4(),
            event_id="support-1",
            correlation_id=uuid.uuid4(),
            idempotency_key="support-1",
            user_id_ref=str(self.user.pk),
            account_id_ref="account-1",
            template_version=1,
            recipient_email=self.user.email,
            event_type="support.case_created",
            locale="en",
        )

        result = EmailMiddlewareClient().submit(item, {"case_id": "case-1"})

        self.assertEqual(result["status"], "QUEUED")
        self.assertEqual(
            post.call_args.args[0],
            "https://middleware.internal/v1/email/messages",
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer service-token",
        )
        token.assert_called_once_with()

    @override_settings(KEYCLOAK_IDENTITY_ENABLED=False)
    @patch.dict(
        "os.environ", {"BEYVRA_EMAIL_API_URL": "https://middleware.internal"}
    )
    @patch.object(EmailMiddlewareClient, "token", return_value="service-token")
    @patch("notifications.email_client.requests.post")
    def test_invalid_middleware_response_is_not_reported_as_success(
        self, post, token
    ):
        response = Mock(status_code=202)
        response.json.side_effect = ValueError("not json")
        post.return_value = response
        item = Mock(
            template_key="support_case_created",
            notification_id=uuid.uuid4(),
            event_id="support-2",
            correlation_id=uuid.uuid4(),
            idempotency_key="support-2",
            user_id_ref=str(self.user.pk),
            account_id_ref="account-1",
            template_version=1,
            recipient_email=self.user.email,
            event_type="support.case_created",
            locale="en",
        )

        with self.assertRaises(EmailMiddlewareError) as raised:
            EmailMiddlewareClient().submit(item, {})

        self.assertEqual(raised.exception.error_class, "INVALID_RESPONSE")
        self.assertFalse(raised.exception.retryable)
