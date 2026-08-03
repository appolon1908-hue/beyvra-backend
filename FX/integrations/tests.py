import hashlib
import json
import time
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from users.models import User
from .models import DemoAccount, DemoLedgerEntry, Organization, ServiceToken


class IntegrationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Synthetic CRM")
        self.token, self.raw = ServiceToken.issue(self.org, "test", ["users:write"])
        self.payload = {"external_user_id": "crm-user-1", "first_name": "Demo", "last_name": "Customer", "email": "demo1@example.invalid", "phone": "+15555550100", "organization_id": str(self.org.id), "consent": {"terms_accepted": True}}

    def test_create_and_idempotent_demo_ledger(self):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.raw}", "HTTP_IDEMPOTENCY_KEY": "synthetic-1"}
        response = self.client.post("/api/v1/users", self.payload, format="json", **headers)
        self.assertEqual(response.status_code, 201)
        replay = self.client.post("/api/v1/users", self.payload, format="json", **headers)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(DemoAccount.objects.count(), 1)
        self.assertEqual(DemoLedgerEntry.objects.get().amount_cents, 200000)
        self.assertFalse(DemoAccount.objects.get().withdrawable)

    def test_caller_cannot_set_balance_or_role(self):
        payload = {**self.payload, "balance": "999999", "role": "Admin"}
        response = self.client.post("/api/v1/users", payload, format="json", HTTP_AUTHORIZATION=f"Bearer {self.raw}", HTTP_IDEMPOTENCY_KEY="synthetic-2")
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email=self.payload["email"])
        self.assertEqual(user.role, "User")
