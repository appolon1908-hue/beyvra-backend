from unittest.mock import patch
from datetime import timedelta
import uuid
from django.utils import timezone

from django.test import override_settings
from django.urls import reverse
from operations.models import AuditEvent, SecurityEvent
from rest_framework.exceptions import APIException
from rest_framework.test import APITestCase
from rest_framework.test import APIClient
from users.models import PendingRegistration, User, EmailVerificationChallenge, TransactionalEmailOutbox
from users.serializers import LoginSerializer


REGISTRATION_ENUMERATION_SETTINGS = {
    "EMAIL_REGISTRATION_ENABLED": True,
    "EMAIL_OTP_VERIFICATION_ENABLED": True,
    "EMAIL_OTP_PEPPER": "enumeration-test-pepper",
    "EMAIL_OTP_TTL_SECONDS": 600,
    "PENDING_REGISTRATION_TTL_SECONDS": 86400,
    "EMAIL_OTP_RESEND_COOLDOWN_SECONDS": 60,
    "TRANSACTIONAL_EMAIL_ENABLED": False,
}


def _registration_payload(email):
    return {
        "email": email,
        "password": "StrongPass9!",
        "displayName": "Enumeration Probe",
        "legalAccepted": True,
    }


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

    @override_settings(**REGISTRATION_ENUMERATION_SETTINGS)
    def test_registration_response_does_not_reveal_account_existence(self):
        known = self.client.post(
            "/api/v1/auth/register",
            _registration_payload(self.user.email),
            format="json",
        )
        unknown = self.client.post(
            "/api/v1/auth/register",
            _registration_payload("unknown@example.test"),
            format="json",
        )

        self.assertEqual(known.status_code, 202)
        self.assertEqual(unknown.status_code, 202)
        # A differing key set is itself an enumeration oracle.
        self.assertEqual(set(known.data), set(unknown.data))
        self.assertTrue(str(known.data["registrationId"]).startswith("reg_"))
        self.assertTrue(PendingRegistration.objects.get(email_normalized=self.user.email).is_decoy)
        self.assertFalse(TransactionalEmailOutbox.objects.filter(recipient_email=self.user.email).exists())

    @override_settings(**REGISTRATION_ENUMERATION_SETTINGS)
    def test_registered_address_returns_a_stable_registration_id(self):
        first = self.client.post(
            "/api/v1/auth/register",
            _registration_payload(self.user.email),
            format="json",
        )
        second = self.client.post(
            "/api/v1/auth/register",
            _registration_payload(self.user.email),
            format="json",
        )
        # A fresh identifier per call would distinguish registered addresses
        # from new ones, which return the same pending row on every retry.
        self.assertEqual(
            first.data["registrationId"], second.data["registrationId"]
        )

    @override_settings(**REGISTRATION_ENUMERATION_SETTINGS)
    def test_registration_and_status_follow_the_same_decoy_lifecycle(self):
        now = timezone.now()
        addresses = [self.user.email, "new@example.test"]
        with patch("users.registration_safety.timezone.now", return_value=now):
            first = [self.client.post("/api/v1/auth/register", _registration_payload(email), format="json").data for email in addresses]
        for body in first:
            self.assertEqual(uuid.UUID(body["registrationId"].removeprefix("reg_")).version, 4)
        with patch("users.registration_safety.timezone.now", return_value=now + timedelta(seconds=2)):
            repeated = [self.client.post("/api/v1/auth/register", _registration_payload(email), format="json").data for email in addresses]
            statuses = [self.client.get("/api/v1/auth/email-verification/status", {"registrationId": body["registrationId"]}).data for body in first]
        for old, new in zip(first, repeated):
            self.assertEqual(old["registrationId"], new["registrationId"])
            self.assertEqual(old["expiresIn"] - new["expiresIn"], 2)
            self.assertEqual(old["registrationExpiresIn"] - new["registrationExpiresIn"], 2)
        self.assertEqual({k:v for k,v in statuses[0].items() if k != "maskedEmail"},
                         {k:v for k,v in statuses[1].items() if k != "maskedEmail"})
        self.assertEqual(statuses[0]["status"], "pending_email_verification")
        with patch("users.registration_safety.timezone.now", return_value=now + timedelta(days=2)):
            renewed = [self.client.post("/api/v1/auth/register", _registration_payload(email), format="json").data for email in addresses]
        for old, new in zip(first, renewed):
            self.assertNotEqual(old["registrationId"], new["registrationId"])
            self.assertEqual(uuid.UUID(new["registrationId"].removeprefix("reg_")).version, 4)

    @override_settings(**REGISTRATION_ENUMERATION_SETTINGS)
    @patch("users.registration_safety.generate_otp", return_value="482913")
    @patch("users.email_verification.generate_otp", return_value="482913")
    def test_decoy_resend_and_verification_cannot_activate_or_send_mail(self, *_):
        now = timezone.now()
        password_before = self.user.password
        with patch("users.registration_safety.timezone.now", return_value=now):
            bodies = [self.client.post("/api/v1/auth/register", _registration_payload(email), format="json").data
                      for email in (self.user.email, "new@example.test")]
        with patch("users.registration_safety.timezone.now", return_value=now + timedelta(seconds=61)):
            resends = [self.client.post("/api/v1/auth/email-verification/resend", {"registrationId": body["registrationId"]}, format="json") for body in bodies]
        self.assertEqual(resends[0].data, resends[1].data)
        self.assertEqual(resends[0].status_code, 200)
        pending = PendingRegistration.objects.get(email_normalized=self.user.email)
        self.assertEqual(pending.challenges.count(), 2)
        self.assertFalse(TransactionalEmailOutbox.objects.filter(recipient_email=self.user.email).exists())
        response = self.client.post("/api/v1/auth/email-verification/verify", {"registrationId": bodies[0]["registrationId"], "code": "482913"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "OTP_INVALID")
        self.assertFalse(response.cookies)
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, password_before)
        self.assertEqual(User.objects.count(), 1)
        pending.refresh_from_db()
        self.assertIsNone(pending.activated_user_id)

    @override_settings(**REGISTRATION_ENUMERATION_SETTINGS)
    def test_registration_rejects_malformed_inputs_and_false_consent(self):
        for payload in ([], {}, {**_registration_payload("bad"), "legalAccepted": True},
                        {**_registration_payload("new@example.test"), "legalAccepted": "false"},
                        {**_registration_payload("new@example.test"), "legalAccepted": 1},
                        {**_registration_payload("new@example.test"), "password": {}},
                        {**_registration_payload("new@example.test"), "password": "x" * 129}):
            with self.subTest(payload=payload):
                response = self.client.post("/api/v1/auth/register", payload, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertFalse(PendingRegistration.objects.exists())

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
