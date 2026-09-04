from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import (
    EmailVerificationChallenge,
    PendingRegistration,
    TransactionalEmailOutbox,
    User,
)
from users.tasks import _otp_delivery_is_current


@override_settings(
    EMAIL_REGISTRATION_ENABLED=True,
    EMAIL_OTP_VERIFICATION_ENABLED=True,
    EMAIL_OTP_PEPPER="integration-otp-pepper",
    EMAIL_OTP_TTL_SECONDS=600,
    PENDING_REGISTRATION_TTL_SECONDS=86400,
    LEGAL_SERVICE_AGREEMENT_VERSION="2026-01",
    LEGAL_PRIVACY_POLICY_VERSION="2026-01",
    LEGAL_RISK_DISCLOSURE_VERSION="2026-01",
)
class EmailVerificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @override_settings(EMAIL_REGISTRATION_ENABLED=False)
    def test_registration_disabled_returns_canonical_code(self):
        response = self.client.post(
            "/api/v1/auth/register",
            {
                "email": "disabled@example.com",
                "password": "StrongPass9!",
                "displayName": "Disabled User",
                "legalAccepted": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.data,
            {
                "code": "EMAIL_REGISTRATION_DISABLED",
                "message": "Registration is temporarily unavailable.",
            },
        )

    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_registration_creates_hashed_otp_and_outbox(self, _):
        response = self.client.post(
            "/api/v1/auth/register",
            {
                "email": "customer@example.com",
                "password": "StrongPass9!",
                "displayName": "Customer Name",
                "legalAccepted": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "pending_email_verification")
        self.assertEqual(PendingRegistration.objects.count(), 1)
        challenge = EmailVerificationChallenge.objects.get()
        self.assertNotEqual(challenge.otp_hash, "482913")
        self.assertEqual(
            TransactionalEmailOutbox.objects.filter(template_key="email_otp").count(),
            1,
        )
        self.assertNotIn("code", response.data)

    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_registration_normalizes_email_case_insensitively(self, _):
        payload = {
            "email": "  Mixed.Email@Example.COM ",
            "password": "StrongPass9!",
            "displayName": "Mixed Email",
            "legalAccepted": True,
        }
        first = self.client.post("/api/v1/auth/register", payload, format="json")
        second = self.client.post(
            "/api/v1/auth/register",
            {**payload, "email": "mixed.email@example.com"},
            format="json",
        )
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.data["registrationId"], second.data["registrationId"])
        self.assertEqual(
            PendingRegistration.objects.get().email_normalized,
            "mixed.email@example.com",
        )

    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_duplicate_submission_reuses_registration_and_active_otp(self, _):
        payload = {
            "email": "duplicate@example.com",
            "password": "StrongPass9!",
            "displayName": "Duplicate User",
            "legalAccepted": True,
        }
        first = self.client.post("/api/v1/auth/register", payload, format="json")
        second = self.client.post("/api/v1/auth/register", payload, format="json")
        self.assertEqual(first.data["registrationId"], second.data["registrationId"])
        self.assertEqual(
            PendingRegistration.objects.filter(
                status="pending_email_verification"
            ).count(),
            1,
        )
        self.assertEqual(
            EmailVerificationChallenge.objects.filter(status="active").count(), 1
        )
        self.assertEqual(
            TransactionalEmailOutbox.objects.filter(template_key="email_otp").count(),
            1,
        )

    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_expired_registration_is_replaced_without_deleting_evidence(self, _):
        payload = {
            "email": "expired@example.com",
            "password": "StrongPass9!",
            "displayName": "Expired User",
            "legalAccepted": True,
        }
        first = self.client.post("/api/v1/auth/register", payload, format="json")
        old = PendingRegistration.objects.get()
        old.expires_at = timezone.now() - timedelta(seconds=1)
        old.save(update_fields=["expires_at"])

        second = self.client.post("/api/v1/auth/register", payload, format="json")

        old.refresh_from_db()
        self.assertEqual(second.status_code, 202)
        self.assertNotEqual(first.data["registrationId"], second.data["registrationId"])
        self.assertEqual(old.status, "expired")
        self.assertEqual(PendingRegistration.objects.count(), 2)
        self.assertEqual(
            EmailVerificationChallenge.objects.filter(status="active").count(), 1
        )
        self.assertEqual(
            EmailVerificationChallenge.objects.filter(status="invalidated").count(),
            1,
        )

    def test_existing_user_response_preserves_email_enumeration_protection(self):
        User.objects.create_user(
            email="existing@example.com",
            password="StrongPass9!",
            first_name="Existing",
            last_name="User",
        )
        response = self.client.post(
            "/api/v1/auth/register",
            {
                "email": "EXISTING@example.com",
                "password": "StrongPass9!",
                "displayName": "Existing User",
                "legalAccepted": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "pending_email_verification")
        self.assertNotIn("registrationId", response.data)
        self.assertFalse(PendingRegistration.objects.exists())

    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_valid_otp_activates_once_and_queues_welcome(self, _):
        registration = self.client.post(
            "/api/v1/auth/register",
            {
                "email": "activate@example.com",
                "password": "StrongPass9!",
                "displayName": "Activate User",
                "legalAccepted": True,
            },
            format="json",
        ).data["registrationId"]
        response = self.client.post(
            "/api/v1/auth/email-verification/verify",
            {"registrationId": registration, "code": "482913"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="activate@example.com")
        self.assertTrue(user.is_active)
        self.assertEqual(user.email_verification_source, "otp")
        self.assertEqual(
            TransactionalEmailOutbox.objects.filter(
                template_key="welcome_email"
            ).count(),
            1,
        )
        replay = self.client.post(
            "/api/v1/auth/email-verification/verify",
            {"registrationId": registration, "code": "482913"},
            format="json",
        )
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(User.objects.filter(email="activate@example.com").count(), 1)

    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_invalid_code_does_not_activate(self, _):
        registration = self.client.post(
            "/api/v1/auth/register",
            {
                "email": "invalid@example.com",
                "password": "StrongPass9!",
                "legalAccepted": True,
            },
            format="json",
        ).data["registrationId"]
        response = self.client.post(
            "/api/v1/auth/email-verification/verify",
            {"registrationId": registration, "code": "000000"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="invalid@example.com").exists())

    def test_status_does_not_expose_code(self):
        response = self.client.get(
            "/api/v1/auth/email-verification/status?registrationId=reg-invalid"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("code", response.data)

    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_expired_otp_outbox_is_not_deliverable(self, _):
        self.client.post(
            "/api/v1/auth/register",
            {
                "email": "stale@example.com",
                "password": "StrongPass9!",
                "legalAccepted": True,
            },
            format="json",
        )
        pending = PendingRegistration.objects.get()
        item = TransactionalEmailOutbox.objects.get(template_key="email_otp")
        pending.expires_at = timezone.now() - timedelta(seconds=1)
        pending.save(update_fields=["expires_at"])
        self.assertFalse(_otp_delivery_is_current(item, timezone.now()))

    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_invalidated_otp_ordinal_cannot_be_delivered_after_resend(self, _):
        self.client.post(
            "/api/v1/auth/register",
            {
                "email": "resend@example.com",
                "password": "StrongPass9!",
                "legalAccepted": True,
            },
            format="json",
        )
        pending = PendingRegistration.objects.get()
        first_item = TransactionalEmailOutbox.objects.get(template_key="email_otp")
        EmailVerificationChallenge.objects.filter(
            registration=pending, status="active"
        ).update(status="invalidated", invalidated_at=timezone.now())
        EmailVerificationChallenge.objects.create(
            registration=pending,
            email_normalized=pending.email_normalized,
            otp_hash="not-used-by-this-test",
            status="active",
            expires_at=timezone.now() + timedelta(minutes=10),
            send_count=2,
        )
        second_item = TransactionalEmailOutbox.objects.create(
            event_type="email_otp_resent",
            event_id="otp-resend-2",
            user_id_ref="registration",
            account_id_ref="registration",
            tenant_id="beyvra",
            recipient_email=pending.email_normalized,
            template_key="email_otp",
            payload={},
            next_attempt_at=timezone.now(),
            idempotency_key=f"otp:{pending.pk}:2",
        )

        self.assertFalse(_otp_delivery_is_current(first_item, timezone.now()))
        self.assertTrue(_otp_delivery_is_current(second_item, timezone.now()))


@override_settings(
    EMAIL_REGISTRATION_ENABLED=True,
    EMAIL_OTP_VERIFICATION_ENABLED=True,
    EMAIL_OTP_PEPPER="concurrency-otp-pepper",
    EMAIL_OTP_TTL_SECONDS=600,
    PENDING_REGISTRATION_TTL_SECONDS=86400,
    LEGAL_SERVICE_AGREEMENT_VERSION="2026-01",
    LEGAL_PRIVACY_POLICY_VERSION="2026-01",
    LEGAL_RISK_DISCLOSURE_VERSION="2026-01",
)
class ConcurrentEmailRegistrationTests(TransactionTestCase):
    reset_sequences = True

    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_concurrent_submissions_create_one_registration_and_active_otp(self, _):
        payload = {
            "email": "concurrent@example.com",
            "password": "StrongPass9!",
            "displayName": "Concurrent User",
            "legalAccepted": True,
        }

        def submit():
            close_old_connections()
            try:
                return APIClient().post(
                    "/api/v1/auth/register", payload, format="json"
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: submit(), range(2)))

        self.assertEqual([response.status_code for response in responses], [202, 202])
        self.assertEqual(
            len({response.data["registrationId"] for response in responses}), 1
        )
        self.assertEqual(
            PendingRegistration.objects.filter(
                status="pending_email_verification"
            ).count(),
            1,
        )
        self.assertEqual(
            EmailVerificationChallenge.objects.filter(status="active").count(), 1
        )
        self.assertEqual(
            TransactionalEmailOutbox.objects.filter(template_key="email_otp").count(),
            1,
        )
