from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from users.models import EmailVerificationChallenge, PendingRegistration, TransactionalEmailOutbox, User


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

    @patch("users.email_verification.generate_otp", return_value="482913")
    def test_registration_creates_hashed_otp_and_outbox(self, _):
        response = self.client.post("/api/v1/auth/register", {"email": "customer@example.com", "password": "StrongPass9!", "displayName": "Customer Name", "legalAccepted": True}, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "pending_email_verification")
        self.assertEqual(PendingRegistration.objects.count(), 1)
        challenge = EmailVerificationChallenge.objects.get()
        self.assertNotEqual(challenge.otp_hash, "482913")
        self.assertEqual(TransactionalEmailOutbox.objects.filter(template_key="email_otp").count(), 1)

    @patch("users.email_verification.generate_otp", return_value="482913")
    def test_valid_otp_activates_once_and_queues_welcome(self, _):
        registration = self.client.post("/api/v1/auth/register", {"email": "activate@example.com", "password": "StrongPass9!", "displayName": "Activate User", "legalAccepted": True}, format="json").data["registrationId"]
        response = self.client.post("/api/v1/auth/email-verification/verify", {"registrationId": registration, "code": "482913"}, format="json")
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="activate@example.com")
        self.assertTrue(user.is_active)
        self.assertEqual(user.email_verification_source, "otp")
        self.assertEqual(TransactionalEmailOutbox.objects.filter(template_key="welcome_email").count(), 1)
        replay = self.client.post("/api/v1/auth/email-verification/verify", {"registrationId": registration, "code": "482913"}, format="json")
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(User.objects.filter(email="activate@example.com").count(), 1)

    @patch("users.email_verification.generate_otp", return_value="482913")
    def test_invalid_code_does_not_activate(self, _):
        registration = self.client.post("/api/v1/auth/register", {"email": "invalid@example.com", "password": "StrongPass9!", "legalAccepted": True}, format="json").data["registrationId"]
        response = self.client.post("/api/v1/auth/email-verification/verify", {"registrationId": registration, "code": "000000"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(email="invalid@example.com").exists())

    def test_status_does_not_expose_code(self):
        response = self.client.get("/api/v1/auth/email-verification/status?registrationId=reg-invalid")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("code", response.data)
