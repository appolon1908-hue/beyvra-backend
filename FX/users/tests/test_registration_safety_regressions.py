from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
from threading import Event
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import (
    EmailVerificationChallenge,
    PendingRegistration,
    TransactionalEmailOutbox,
)
from users.tasks import process_transactional_email_outbox


REGISTRATION_SETTINGS = {
    "EMAIL_REGISTRATION_ENABLED": True,
    "EMAIL_OTP_VERIFICATION_ENABLED": True,
    "EMAIL_OTP_PEPPER": "registration-regression-pepper",
    "EMAIL_OTP_TTL_SECONDS": 600,
    "PENDING_REGISTRATION_TTL_SECONDS": 86400,
    "EMAIL_OTP_RESEND_COOLDOWN_SECONDS": 60,
    "EMAIL_OTP_MAX_SENDS_PER_HOUR": 5,
    "LEGAL_SERVICE_AGREEMENT_VERSION": "2026-01",
    "LEGAL_PRIVACY_POLICY_VERSION": "2026-01",
    "LEGAL_RISK_DISCLOSURE_VERSION": "2026-01",
    "TRANSACTIONAL_EMAIL_ENABLED": False,
}


def registration_payload(email: str) -> dict:
    return {
        "email": email,
        "password": "StrongPass9!",
        "displayName": "Registration Regression",
        "legalAccepted": True,
    }


@override_settings(**REGISTRATION_SETTINGS)
class RegistrationSafetyResponseTests(TestCase):
    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_registration_reports_challenge_and_registration_expiry_separately(
        self, _
    ):
        response = APIClient().post(
            "/api/v1/auth/register",
            registration_payload("expiry-contract@example.com"),
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertGreater(response.data["expiresIn"], 0)
        self.assertLessEqual(
            response.data["expiresIn"], settings.EMAIL_OTP_TTL_SECONDS
        )
        self.assertGreater(
            response.data["registrationExpiresIn"], response.data["expiresIn"]
        )

    def test_migration_normalizes_linked_challenge_identity(self):
        now = timezone.now()
        pending = PendingRegistration.objects.create(
            email_normalized="Mixed.Case@Example.COM",
            display_name="Legacy Registration",
            password_hash="not-used",
            legal_confirmation=True,
            legal_document_versions={},
            expires_at=now + timedelta(hours=1),
        )
        challenge = EmailVerificationChallenge.objects.create(
            registration=pending,
            email_normalized="Mixed.Case@Example.COM",
            otp_hash="not-used",
            expires_at=now + timedelta(minutes=10),
            max_attempts=5,
            send_count=1,
        )

        migration = import_module(
            "users.migrations.0037_pending_registration_concurrency"
        )
        migration.reconcile_pending_registration_evidence(apps, None)

        pending.refresh_from_db()
        challenge.refresh_from_db()
        self.assertEqual(pending.email_normalized, "mixed.case@example.com")
        self.assertEqual(challenge.email_normalized, pending.email_normalized)


@override_settings(**REGISTRATION_SETTINGS)
class RegistrationDeliverySerializationTests(TransactionTestCase):
    reset_sequences = True

    @patch("users.registration_safety.generate_otp", return_value="482913")
    def test_resend_waits_until_checked_otp_delivery_finishes(self, _):
        if not connection.features.has_select_for_update:
            self.skipTest("database does not support row-level select_for_update")

        client = APIClient()
        registration_id = client.post(
            "/api/v1/auth/register",
            registration_payload("serialized-delivery@example.com"),
            format="json",
        ).data["registrationId"]
        pending = PendingRegistration.objects.get()
        challenge = EmailVerificationChallenge.objects.get(
            registration=pending, status="active"
        )
        EmailVerificationChallenge.objects.filter(pk=challenge.pk).update(
            last_sent_at=timezone.now()
            - timedelta(
                seconds=settings.EMAIL_OTP_RESEND_COOLDOWN_SECONDS + 1
            )
        )

        provider_started = Event()
        release_provider = Event()
        resend_finished = Event()

        def provider_response(_item):
            provider_started.set()
            if not release_provider.wait(timeout=10):
                raise AssertionError("provider test gate timed out")
            return {"notification_id": "serialized-otp", "status": "QUEUED"}

        def deliver():
            close_old_connections()
            try:
                return process_transactional_email_outbox.run()
            finally:
                close_old_connections()

        def resend():
            close_old_connections()
            try:
                response = APIClient().post(
                    "/api/v1/auth/email-verification/resend",
                    {"registrationId": registration_id},
                    format="json",
                )
                resend_finished.set()
                return response
            finally:
                close_old_connections()

        with patch(
            "users.tasks.send_outbox_message", side_effect=provider_response
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                delivery_future = executor.submit(deliver)
                self.assertTrue(provider_started.wait(timeout=10))
                resend_future = executor.submit(resend)

                # The resend transaction takes the same pending-registration
                # row lock and therefore cannot invalidate the checked code
                # while its bounded provider transition is in progress.
                self.assertFalse(resend_finished.wait(timeout=0.25))
                release_provider.set()

                self.assertEqual(delivery_future.result(timeout=10), "sent")
                response = resend_future.result(timeout=10)

        self.assertEqual(response.status_code, 200)
        first_item = TransactionalEmailOutbox.objects.get(
            idempotency_key=f"otp:{pending.pk}:1"
        )
        self.assertEqual(first_item.status, "sent")
        self.assertEqual(
            EmailVerificationChallenge.objects.get(
                registration=pending, status="active"
            ).send_count,
            2,
        )
