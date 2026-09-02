from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.foundation.models import ApplicationAuditEvent
from integrations.models import Organization, OrganizationMembership
from security.models import IPWhitelist


class SecurityCommandTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.organization = Organization.objects.create(name="Security test tenant")
        self.other_organization = Organization.objects.create(name="Other security tenant")
        self.admin = get_user_model().objects.create_user(
            email="security-admin@example.test", password="test-only", is_staff=True,
        )
        self.other_admin = get_user_model().objects.create_user(
            email="other-security-admin@example.test", password="test-only", is_staff=True,
        )
        self.other_user = get_user_model().objects.create_user(
            email="other-security-user@example.test", password="test-only",
        )
        OrganizationMembership.objects.create(user=self.admin, organization=self.organization, role="owner")
        OrganizationMembership.objects.create(user=self.other_admin, organization=self.other_organization, role="owner")
        OrganizationMembership.objects.create(user=self.other_user, organization=self.other_organization, role="member")
        self.client.force_authenticate(self.admin)
        self.headers = {
            "HTTP_X_ORGANIZATION_ID": str(self.organization.pk),
            "HTTP_IDEMPOTENCY_KEY": "security-command-test",
            "HTTP_X_REQUEST_ID": "467dc5f9-0274-43de-ab92-f48d907a9011",
        }

    def test_ip_whitelist_create_replays_and_conflicts(self):
        first = self.client.post("/api/security/ip-whitelist/", {"ip_address": "198.51.100.10"}, format="json", **self.headers)
        replay = self.client.post("/api/security/ip-whitelist/", {"ip_address": "198.51.100.10"}, format="json", **self.headers)
        conflict = self.client.post("/api/security/ip-whitelist/", {"ip_address": "198.51.100.11"}, format="json", **self.headers)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(IPWhitelist.objects.filter(admin=self.admin).count(), 1)
        self.assertEqual(ApplicationAuditEvent.objects.filter(action="security.ip_whitelist.create").count(), 1)

    def test_admin_cannot_delete_another_admins_entry(self):
        entry = IPWhitelist.objects.create(admin=self.other_admin, ip_address="198.51.100.20")
        response = self.client.delete(
            f"/api/security/ip-whitelist/{entry.pk}/delete/", format="json",
            **{**self.headers, "HTTP_IF_MATCH": entry.updated_at.isoformat().replace("+00:00", "Z")},
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(IPWhitelist.objects.filter(pk=entry.pk).exists())

    def test_delete_rejects_stale_version(self):
        entry = IPWhitelist.objects.create(admin=self.admin, ip_address="198.51.100.30")
        response = self.client.delete(
            f"/api/security/ip-whitelist/{entry.pk}/delete/", format="json",
            **{**self.headers, "HTTP_IF_MATCH": "stale-version"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(IPWhitelist.objects.filter(pk=entry.pk).exists())

    def test_cross_tenant_user_security_mutation_is_hidden(self):
        response = self.client.patch(
            f"/api/security/users/{self.other_user.pk}/set-2fa-type/",
            {"two_factor_auth_type": "SMS"}, format="json",
            **{**self.headers, "HTTP_IF_MATCH": self.other_user.updated_at.isoformat().replace("+00:00", "Z")},
        )
        self.assertEqual(response.status_code, 404)
