import hashlib
import json
import time
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from users.models import User
from apps.foundation.models import IdempotencyRecord
from .models import DemoAccount, DemoLedgerEntry, Organization, OrganizationMembership, ServiceToken


@override_settings(API_TOKEN_PEPPER="integration-test-pepper")
class IntegrationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Synthetic CRM")
        self.token, self.raw = ServiceToken.issue(self.org, "test", ["users:write"])
        self.payload = {"external_user_id": "crm-user-1", "first_name": "Demo", "last_name": "Customer", "email": "demo1@example.invalid", "phone": "+15555550100", "organization_id": str(self.org.id), "consent": {"terms_accepted": True}}

    def test_create_and_idempotent_demo_ledger(self):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.raw}", "HTTP_IDEMPOTENCY_KEY": "synthetic-1", "HTTP_X_REQUEST_ID": "84acb666-d825-4dba-b579-c7feb4af2001"}
        response = self.client.post("/api/v1/users", self.payload, format="json", **headers)
        self.assertEqual(response.status_code, 201)
        replay = self.client.post("/api/v1/users", self.payload, format="json", **headers)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(DemoAccount.objects.count(), 1)
        self.assertEqual(DemoLedgerEntry.objects.get().amount_cents, 200000)
        self.assertFalse(DemoAccount.objects.get().withdrawable)
        conflict = self.client.post("/api/v1/users", {**self.payload, "email": "changed@example.invalid"}, format="json", **headers)
        self.assertEqual(conflict.status_code, 409)

    def test_caller_cannot_set_balance_or_role(self):
        payload = {**self.payload, "balance": "999999", "role": "Admin"}
        response = self.client.post("/api/v1/users", payload, format="json", HTTP_AUTHORIZATION=f"Bearer {self.raw}", HTTP_IDEMPOTENCY_KEY="synthetic-2", HTTP_X_REQUEST_ID="84acb666-d825-4dba-b579-c7feb4af2002")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email=self.payload["email"])
        self.assertEqual(user.role, "User")


@override_settings(API_TOKEN_PEPPER="integration-test-pepper", DATA_ENCRYPTION_KEY="integration-test-data-key")
class IntegrationManagementCommandTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Integration management")
        self.admin = User.objects.create_user(email="integration-admin@example.test", password="test-only", is_staff=True)
        OrganizationMembership.objects.create(user=self.admin, organization=self.org, role="owner")
        self.client.force_authenticate(self.admin)

    def test_service_token_issue_replays_encrypted_secret(self):
        headers = {
            "HTTP_X_ORGANIZATION_ID": str(self.org.id), "HTTP_IDEMPOTENCY_KEY": "token-issue-test",
            "HTTP_X_REQUEST_ID": "84acb666-d825-4dba-b579-c7feb4af2003",
        }
        payload = {"name": "automation", "scopes": ["users:read"]}
        first = self.client.post("/api/v1/integrations/service-tokens", payload, format="json", **headers)
        replay = self.client.post("/api/v1/integrations/service-tokens", payload, format="json", **headers)
        conflict = self.client.post("/api/v1/integrations/service-tokens", {**payload, "scopes": ["users:write"]}, format="json", **headers)
        self.assertEqual(first.status_code, 201); self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.data, first.data); self.assertEqual(conflict.status_code, 409)
        self.assertEqual(ServiceToken.objects.filter(owner=self.admin).count(), 1)
        stored = IdempotencyRecord.objects.get(key="token-issue-test").response_body
        self.assertNotIn(first.data["token"], json.dumps(stored))
