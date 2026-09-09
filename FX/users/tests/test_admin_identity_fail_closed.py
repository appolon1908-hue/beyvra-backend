from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(LOCAL_PASSWORD_AUTH_ENABLED=True)
class AdminIdentityFailClosedTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            email="identity-admin@example.test", password="admin-test-only", is_staff=True,
        )
        self.user = get_user_model().objects.create_user(
            email="identity-user@example.test", password="original-test-only",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_hard_delete_is_disabled(self):
        response = self.client.delete(f"/api/admin/users/{self.user.pk}/delete/", {"confirm": True}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "ACCOUNT_CLOSURE_WORKFLOW_REQUIRED")
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_bulk_password_reset_is_disabled_without_credential_change(self):
        response = self.client.post(
            "/api/admin/users/bulk-reset-password/",
            {"user_ids": [self.user.pk], "new_password": "shared-unsafe-value", "confirm_password": "shared-unsafe-value"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("original-test-only"))

    def test_non_admin_cannot_inspect_another_users_permissions(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/admin/users/rbac/users/check-permissions/",
            {"user_id": self.admin.pk, "permission": "auth.change_user"}, format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_self_service_hard_delete_is_disabled(self):
        self.client.force_authenticate(self.user)
        response = self.client.delete("/api/user/delete/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
