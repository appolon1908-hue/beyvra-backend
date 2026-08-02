import pyotp
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class MFALoginSecurityTests(APITestCase):
    def setUp(self):
        self.password = "a-secure-test-password"
        self.secret = pyotp.random_base32()
        self.user = get_user_model().objects.create_user(
            email="mfa@example.com",
            password=self.password,
            first_name="Mfa",
            last_name="User",
            phone_number="+12025550123",
            mfa_secret=self.secret,
            is_mfa_enabled=True,
            two_factor_authentication_enabled=True,
        )

    def test_password_login_does_not_issue_tokens_before_mfa(self):
        response = self.client.post(
            reverse("user:token_obtain_pair"),
            {"email": self.user.email, "password": self.password},
            HTTP_USER_AGENT="test-client/1.0",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(response.data["mfa_required"])
        self.assertIn("login_token", response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_valid_mfa_challenge_issues_tokens(self):
        login = self.client.post(
            reverse("user:token_obtain_pair"),
            {"email": self.user.email, "password": self.password},
            HTTP_USER_AGENT="test-client/1.0",
            REMOTE_ADDR="127.0.0.1",
        )
        response = self.client.post(
            reverse("user:verify_mfa"),
            {"login_token": login.data["login_token"], "otp": pyotp.TOTP(self.secret).now()},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
