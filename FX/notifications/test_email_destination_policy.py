"""No-network regressions for the exact Middleware destination boundary."""
import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from notifications import email_client


class EmailDestinationPolicyTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "BEYVRA_EMAIL_API_URL": "https://middleware.internal",
            "BEYVRA_EMAIL_ALLOWED_ORIGINS": "https://middleware.internal",
        }))
        self.enterContext(patch.object(email_client, "settings", SimpleNamespace(
            KEYCLOAK_IDENTITY_ENABLED=False,
            BEYVRA_EMAIL_API_URL="",
            BEYVRA_EMAIL_ALLOWED_ORIGINS=(),
        )))
        self.post = self.enterContext(patch.object(email_client.requests, "post"))
        self.token = self.enterContext(patch.object(
            email_client.EmailMiddlewareClient, "token", return_value="test-token"
        ))
        self.effects = self.enterContext(patch.object(email_client, "record_live_effect"))
        self.item = SimpleNamespace(
            template_key="support_case_created", notification_id="notice-1",
            event_id="event-1", correlation_id="correlation-1",
            idempotency_key="support:event-1", user_id_ref="user-1",
            account_id_ref="account-1", template_version=1,
            recipient_email="recipient@example.test",
            event_type="support.case_created", locale="en",
        )
        self.client = email_client.EmailMiddlewareClient()

    def assert_blocked(self, error_class, retryable=False):
        with self.assertRaises(email_client.EmailMiddlewareError) as raised:
            self.client.submit(self.item, {"case_id": "case-1"})
        self.assertEqual(raised.exception.error_class, error_class)
        self.assertEqual(raised.exception.retryable, retryable)
        self.token.assert_not_called()
        self.post.assert_not_called()
        self.effects.assert_not_called()

    def test_unlisted_destinations_never_receive_credentials_or_message(self):
        for origin in (
            "https://example.com", "https://middleware.internal.example.com",
            "https://other.internal", "https://127.0.0.1",
            "http://169.254.169.254", "http://middleware.internal",
            "https://middleware.internal:8443",
            "http://[::1]", "http://[::ffff:127.0.0.1]",
            "http://[fe80::1]", "https://[fd00::2]",
        ):
            with self.subTest(origin=origin):
                os.environ["BEYVRA_EMAIL_API_URL"] = origin
                self.assert_blocked("DIRECT_INTEGRATION_BYPASS_BLOCKED")

    def test_missing_allowlist_keeps_intent_retryable(self):
        os.environ["BEYVRA_EMAIL_ALLOWED_ORIGINS"] = ""
        self.assert_blocked("MIDDLEWARE_ALLOWLIST_NOT_CONFIGURED", True)

    def test_absent_allowlist_has_no_implicit_destination_default(self):
        os.environ.pop("BEYVRA_EMAIL_ALLOWED_ORIGINS")
        self.assert_blocked("MIDDLEWARE_ALLOWLIST_NOT_CONFIGURED", True)

    def test_missing_destination_keeps_intent_retryable(self):
        os.environ["BEYVRA_EMAIL_API_URL"] = ""
        self.assert_blocked("MIDDLEWARE_ENDPOINT_NOT_CONFIGURED", True)

    def test_legacy_public_fallback_remains_retryable(self):
        os.environ.pop("BEYVRA_EMAIL_API_URL")
        email_client.settings.BEYVRA_EMAIL_API_URL = "https://api.codestra.co"
        self.assert_blocked("MIDDLEWARE_ENDPOINT_NOT_CONFIGURED", True)

    def test_known_bypasses_cannot_be_added_to_allowlist(self):
        for host in ("api.codestra.co", "api.codestra.agency", "api.klyrow.com", "mail.klyrow.com"):
            with self.subTest(host=host):
                os.environ["BEYVRA_EMAIL_API_URL"] = f"https://{host.upper()}."
                os.environ["BEYVRA_EMAIL_ALLOWED_ORIGINS"] = f"https://{host}"
                self.assert_blocked("DIRECT_INTEGRATION_BYPASS_BLOCKED")

    def test_malformed_urls_are_classified_before_token_acquisition(self):
        for origin in (
            "https://middleware.internal:bad", "https://middleware.internal:99999",
            "https://[invalid", "https://@middleware.internal",
            "https://user:password@middleware.internal", "https://middleware.internal/path",
            "https://middleware.internal?x=1", "https://middleware.internal#fragment",
            "https://middleware.internal?", "https://middleware.internal#",
            "https://middleware.in\nternal", "https://%6diddleware.internal",
            "https://middleware.internal\\example.com", "ftp://middleware.internal",
            "https://middleware.internal..",
            "https://[fd00::1]ignored", "https://[fd00::1]:",
            "https://[fe80::1%eth0]", "https://[fe80::1%25eth0]",
            "https://[fd00::1]:443:80",
        ):
            with self.subTest(origin=origin):
                os.environ["BEYVRA_EMAIL_API_URL"] = origin
                self.assert_blocked("MIDDLEWARE_ENDPOINT_INVALID")

    def test_malformed_allowlist_fails_closed(self):
        for allowed in ("*", "https://*.internal", "https://middleware.internal,", "https://middleware.internal/path"):
            with self.subTest(allowed=allowed):
                os.environ["BEYVRA_EMAIL_ALLOWED_ORIGINS"] = allowed
                self.assert_blocked("MIDDLEWARE_ALLOWLIST_INVALID")

    def test_matching_normalized_origin_is_the_actual_request_destination(self):
        os.environ["BEYVRA_EMAIL_API_URL"] = "HTTPS://MIDDLEWARE.INTERNAL.:443/"
        self.post.return_value = Mock(status_code=202)
        self.post.return_value.json.return_value = {"status": "QUEUED"}
        self.assertEqual(self.client.submit(self.item, {}), {"status": "QUEUED"})
        self.post.assert_called_once()
        self.assertEqual(self.post.call_args.args[0], "https://middleware.internal/v1/email/messages")
        self.assertFalse(self.post.call_args.kwargs["allow_redirects"])
        self.token.assert_called_once_with()

    def test_explicit_nondefault_origin_and_ipv6_normalization(self):
        for destination, allowed in (
            ("https://middleware.internal:8443", "https://middleware.internal:8443"),
            ("https://[fd00:0:0::1]:443/", "https://[fd00::1]"),
        ):
            with self.subTest(destination=destination):
                os.environ["BEYVRA_EMAIL_API_URL"] = destination
                os.environ["BEYVRA_EMAIL_ALLOWED_ORIGINS"] = allowed
                self.assertEqual(self.client._middleware_base_url(), allowed)

    def test_settings_allowlist_is_independent_from_destination(self):
        os.environ.pop("BEYVRA_EMAIL_ALLOWED_ORIGINS")
        email_client.settings.BEYVRA_EMAIL_ALLOWED_ORIGINS = ("https://middleware.internal",)
        self.assertEqual(self.client._middleware_base_url(), "https://middleware.internal")
        os.environ["BEYVRA_EMAIL_API_URL"] = "https://example.com"
        self.assert_blocked("DIRECT_INTEGRATION_BYPASS_BLOCKED")

    def test_empty_environment_overrides_nonempty_settings_allowlist(self):
        email_client.settings.BEYVRA_EMAIL_ALLOWED_ORIGINS = ("https://middleware.internal",)
        os.environ["BEYVRA_EMAIL_ALLOWED_ORIGINS"] = ""
        self.assert_blocked("MIDDLEWARE_ALLOWLIST_NOT_CONFIGURED", True)

    def test_keycloak_identity_mail_never_acquires_business_mail_token(self):
        email_client.settings.KEYCLOAK_IDENTITY_ENABLED = True
        for template in ("password_reset", "account_verification", "email_otp"):
            with self.subTest(template=template):
                self.item.template_key = template
                self.assert_blocked("IDENTITY_MAIL_MUST_USE_KEYCLOAK")

    def test_redirects_are_not_reported_as_success(self):
        for status in (301, 302, 307, 308):
            with self.subTest(status=status):
                self.post.return_value = Mock(status_code=status)
                self.effects.reset_mock()
                with self.assertRaises(email_client.EmailMiddlewareError) as raised:
                    self.client.submit(self.item, {})
                self.assertEqual(raised.exception.error_class, "INVALID_RESPONSE")
                self.assertNotIn((("transactional_email", "success"),), self.effects.call_args_list)

    def test_nonobject_json_is_not_reported_as_success(self):
        for body in ([], None, "ok", 1):
            with self.subTest(body=body):
                self.post.return_value = Mock(status_code=202)
                self.post.return_value.json.return_value = body
                with self.assertRaises(email_client.EmailMiddlewareError) as raised:
                    self.client.submit(self.item, {})
                self.assertEqual(raised.exception.error_class, "INVALID_RESPONSE")

    def test_malformed_ipv6_allowlist_is_rejected(self):
        for origin in ("https://[fd00::1]ignored", "https://[fe80::1%25eth0]"):
            with self.subTest(origin=origin):
                os.environ["BEYVRA_EMAIL_ALLOWED_ORIGINS"] = origin
                self.assert_blocked("MIDDLEWARE_ALLOWLIST_INVALID")

    def test_ipv6_equivalent_forms_use_one_canonical_destination(self):
        os.environ["BEYVRA_EMAIL_API_URL"] = "https://[FD00:0:0:0:0:0:0:1]:443/"
        os.environ["BEYVRA_EMAIL_ALLOWED_ORIGINS"] = "https://[fd00::1]"
        self.post.return_value = Mock(status_code=202)
        self.post.return_value.json.return_value = {"status": "QUEUED"}
        self.client.submit(self.item, {})
        self.assertEqual(self.post.call_args.args[0], "https://[fd00::1]/v1/email/messages")
        self.assertFalse(self.post.call_args.kwargs["allow_redirects"])
