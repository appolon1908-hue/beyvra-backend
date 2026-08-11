from unittest.mock import patch

from django.urls import reverse
from operations.models import SecurityEvent
from rest_framework.exceptions import APIException
from rest_framework.test import APITestCase
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
