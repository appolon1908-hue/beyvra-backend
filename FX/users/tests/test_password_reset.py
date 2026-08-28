from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import TransactionalEmailOutbox


class PasswordResetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email="reset@example.com",
            password="OriginalPass9!",
            first_name="Reset",
            last_name="User",
            phone_number="+12025550181",
        )

    def test_request_sends_reset_email_for_case_insensitive_match(self):
        response = self.client.post(reverse("user:password_reset"), {"email": "RESET@EXAMPLE.COM"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = TransactionalEmailOutbox.objects.get()
        self.assertEqual(item.recipient_email, self.user.email)
        self.assertEqual(item.template_key, "password_reset")
        self.assertIn("/password-reset?uidb64=", item.payload["action"])
        self.assertIn("&token=", item.payload["action"])

    def test_request_does_not_reveal_missing_account(self):
        existing_response = self.client.post(reverse("user:password_reset"), {"email": self.user.email})
        missing_response = self.client.post(reverse("user:password_reset"), {"email": "missing@example.com"})

        self.assertEqual(existing_response.status_code, status.HTTP_200_OK)
        self.assertEqual(missing_response.status_code, status.HTTP_200_OK)
        self.assertEqual(existing_response.data, missing_response.data)
        self.assertEqual(TransactionalEmailOutbox.objects.count(), 1)

    def test_confirm_changes_password_and_revokes_refresh_tokens(self):
        refresh = RefreshToken.for_user(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.client.post(
            reverse("user:password_reset_confirm", kwargs={"uidb64": uid, "token": token}),
            {"new_password": "ReplacementPass9!", "new_password_confirm": "ReplacementPass9!"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ReplacementPass9!"))
        self.assertTrue(BlacklistedToken.objects.filter(token__token=str(refresh)).exists())

    def test_confirm_rejects_invalid_link_and_weak_password(self):
        invalid_link = self.client.post(
            reverse("user:password_reset_confirm", kwargs={"uidb64": "bad", "token": "bad"}),
            {"new_password": "ReplacementPass9!", "new_password_confirm": "ReplacementPass9!"},
        )
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        weak_password = self.client.post(
            reverse("user:password_reset_confirm", kwargs={"uidb64": uid, "token": token}),
            {"new_password": "password", "new_password_confirm": "password"},
        )

        self.assertEqual(invalid_link.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(weak_password.status_code, status.HTTP_400_BAD_REQUEST)
