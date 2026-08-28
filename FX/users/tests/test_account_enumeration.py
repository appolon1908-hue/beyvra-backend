from unittest.mock import patch

from django.urls import reverse
from operations.models import AuditEvent, SecurityEvent
from rest_framework.exceptions import APIException
from rest_framework.test import APITestCase
from rest_framework.test import APIClient
from users.models import User
from users.serializers import LoginSerializer


class AccountEnumerationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="known@example.test",
            password="safe-test-password",
            phone_number="+12025550161",
        )

    @patch("users.views.async_send_password_reset_link_email.delay")
    def test_password_reset_response_does_not_reveal_account_existence(self, delay):
        known = self.client.post(
            reverse("user:password_reset"), {"email": self.user.email}, format="json"
        )
        unknown = self.client.post(
            reverse("user:password_reset"),
            {"email": "unknown@example.test"},
            format="json",
        )
        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.data, unknown.data)
        delay.assert_called_once_with(self.user.pk)

    def test_known_account_failures_create_safe_escalating_signals(self):
        for _ in range(5):
            serializer = LoginSerializer(
                data={"email": self.user.email, "password": "incorrect-password"}
            )
            with self.assertRaises(APIException):
                serializer.is_valid(raise_exception=True)
        events = SecurityEvent.objects.filter(
            account=self.user, event_type="LOGIN_FAILURE"
        ).order_by("occurred_at")
        self.assertEqual(events.count(), 5)
        self.assertEqual(events.last().risk_level, "HIGH")
        self.assertEqual(
            events.last().metadata_safe["reason_code"], "TOO_MANY_FAILED_LOGINS"
        )

    def test_unknown_account_does_not_create_fabricated_security_event(self):
        serializer = LoginSerializer(
            data={"email": "unknown@example.test", "password": "incorrect-password"}
        )
        with self.assertRaises(APIException):
            serializer.is_valid(raise_exception=True)
        self.assertFalse(SecurityEvent.objects.exists())

    def test_many_failures_deny_later_valid_password_without_issuing_tokens(self):
        for _ in range(5):
            self.client.post(
                reverse("user:token_obtain_pair"),
                {"email": self.user.email, "password": "incorrect-password"},
                format="json",
                HTTP_USER_AGENT="known-browser/1",
                REMOTE_ADDR="192.0.2.10",
            )
        response = self.client.post(
            reverse("user:token_obtain_pair"),
            {"email": self.user.email, "password": "safe-test-password"},
            format="json",
            HTTP_USER_AGENT="known-browser/1",
            REMOTE_ADDR="192.0.2.10",
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)
        audit = AuditEvent.objects.filter(
            actor=self.user, action="ACCOUNT_RISK_EVALUATED"
        ).latest("timestamp")
        self.assertEqual(audit.metadata_safe["decision"], "DENY")
        self.assertIn(
            "TOO_MANY_FAILED_LOGINS", audit.metadata_safe["reason_codes"]
        )

    def test_new_device_requires_step_up_when_account_has_no_mfa(self):
        initial = self.client.post(
            reverse("user:token_obtain_pair"),
            {"email": self.user.email, "password": "safe-test-password"},
            format="json",
            HTTP_USER_AGENT="known-browser/1",
            REMOTE_ADDR="192.0.2.10",
        )
        self.assertEqual(initial.status_code, 200)
        response = self.client.post(
            reverse("user:token_obtain_pair"),
            {"email": self.user.email, "password": "safe-test-password"},
            format="json",
            HTTP_USER_AGENT="new-browser/2",
            REMOTE_ADDR="192.0.2.11",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "STEP_UP_REQUIRED")
        self.assertNotIn("access", response.data)
        audit = AuditEvent.objects.filter(
            actor=self.user, action="ACCOUNT_RISK_EVALUATED"
        ).latest("timestamp")
        self.assertEqual(audit.metadata_safe["decision"], "STEP_UP")
        self.assertEqual(
            set(audit.metadata_safe["reason_codes"]), {"NEW_DEVICE", "NEW_NETWORK"}
        )

    def test_browser_session_uses_http_only_cookies_and_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        login = client.post(
            reverse("user:token_obtain_pair"),
            {"email": self.user.email, "password": "safe-test-password"},
            format="json",
            HTTP_USER_AGENT="secure-browser/1",
            REMOTE_ADDR="192.0.2.20",
        )
        self.assertEqual(login.status_code, 200)
        for name in ("beyvra_access", "beyvra_refresh"):
            self.assertIn(name, login.cookies)
            self.assertTrue(login.cookies[name]["httponly"])
            self.assertTrue(login.cookies[name]["secure"])
            self.assertEqual(login.cookies[name]["samesite"], "Strict")
        for name in ("access_token", "refresh_token"):
            self.assertEqual(login.cookies[name].value, "session")
            self.assertFalse(login.cookies[name]["httponly"])
            self.assertNotIn(".", login.cookies[name].value)
        self.assertEqual(client.get("/api/v1/security/sessions").status_code, 200)
        self.assertEqual(client.post("/api/v1/notifications/read-all").status_code, 403)
        csrf_token = login.cookies["csrftoken"].value
        self.assertEqual(
            client.post(
                "/api/v1/notifications/read-all", HTTP_X_CSRFTOKEN=csrf_token
            ).status_code,
            204,
        )
        self.assertEqual(
            client.post(reverse("user:token_refresh"), {}, format="json").status_code,
            403,
        )
        refreshed = client.post(
            reverse("user:token_refresh"),
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertTrue(refreshed.cookies["beyvra_access"]["httponly"])
