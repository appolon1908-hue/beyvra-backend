from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


class LogoutSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            email="logout@example.com",
            password="test-pass",
            phone_number="+12025550131",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_logout_blacklists_own_refresh_token(self):
        refresh = RefreshToken.for_user(self.user)

        response = self.client.post(
            "/api/user/token/logout/", {"refresh": str(refresh)}, format="json", secure=True
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh_response = APIClient().post(
            "/api/user/token/refresh/", {"refresh": str(refresh)}, format="json", secure=True
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_rejects_another_users_refresh_token(self):
        other_user = get_user_model().objects.create_user(
            email="other-logout@example.com",
            password="test-pass",
            phone_number="+12025550132",
        )
        refresh = RefreshToken.for_user(other_user)

        response = self.client.post(
            "/api/user/token/logout/", {"refresh": str(refresh)}, format="json", secure=True
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("does not belong", str(response.data))
