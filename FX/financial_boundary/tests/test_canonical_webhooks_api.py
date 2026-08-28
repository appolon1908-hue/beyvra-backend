import json
import time
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from provider_governance.models import ProviderApproval, ProviderDefinition, ProviderLicense
from financial_boundary.models import ProviderWebhookInbox
from financial_boundary.webhooks import webhook_signature

SECRET = "provider-specific-secret-with-more-than-32-bytes"
TENANT_REF = "11111111-1111-1111-1111-111111111111"

SIMULATION = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
)


@SIMULATION
class CanonicalProviderWebhooksApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.provider = ProviderDefinition.objects.create(
            provider_id="alpaca",
            provider_type="EXECUTION",
            enabled=True,
            license_verified=True,
            security_approved=True,
            compliance_approved=True,
            staging_approved=True,
        )
        license_record = ProviderLicense.objects.create(
            provider=self.provider,
            environment="STAGING",
            status="APPROVED",
            license_reference="license:test:webhook",
        )
        ProviderApproval.objects.create(
            provider=self.provider,
            provider_type="EXECUTION",
            environment="STAGING",
            version=1,
            status="APPROVED",
            approved_by_principal_id="security-reviewer",
            approved_at=timezone.now(),
            approval_reference="approval:test:webhook",
            license=license_record,
            credential_policy="NONE",
            approval_payload_hash="0" * 64,
            created_by="test",
        )

    @patch.dict("os.environ", {"PROVIDER_WEBHOOK_SECRET_ALPACA": SECRET})
    def test_ingest_valid_provider_webhook(self):
        now = int(time.time())
        event_id = "evt_alpaca_1001"
        provider = "alpaca"
        body = json.dumps({"event_type": "financial.trade.execution.v1", "order_id": "ord_1001"}).encode("utf-8")
        sig = webhook_signature(
            provider_id=provider,
            event_id=event_id,
            timestamp=now,
            raw_body=body,
            secret=SECRET.encode("utf-8"),
        )

        headers = {
            "HTTP_X_PROVIDER_ID": provider,
            "HTTP_X_EVENT_ID": event_id,
            "HTTP_X_TIMESTAMP": str(now),
            "HTTP_X_SIGNATURE": sig,
            "HTTP_X_TENANT_REF": TENANT_REF,
        }

        res = self.client.post(
            f"/api/v1/webhooks/executions/{provider}",
            body,
            content_type="application/json",
            **headers,
        )
        self.assertEqual(res.status_code, 202)
        self.assertEqual(res.json()["status"], "accepted")
        self.assertEqual(ProviderWebhookInbox.objects.count(), 1)
        inbox = ProviderWebhookInbox.objects.get()
        self.assertEqual(inbox.provider, provider)
        self.assertEqual(inbox.external_event_id, event_id)
        self.assertEqual(inbox.tenant_id.hex, TENANT_REF.replace("-", ""))
        self.assertEqual(inbox.status, ProviderWebhookInbox.Status.PENDING)

        # Duplicate submission
        res_dup = self.client.post(
            f"/api/v1/webhooks/executions/{provider}",
            body,
            content_type="application/json",
            **headers,
        )
        self.assertEqual(res_dup.status_code, 200)
        self.assertEqual(res_dup.json()["status"], "duplicate")
        self.assertEqual(ProviderWebhookInbox.objects.count(), 1)

    def test_ingest_disallowed_provider(self):
        res = self.client.post("/api/v1/webhooks/executions/untrusted_broker", b"{}", content_type="application/json")
        self.assertEqual(res.status_code, 403)

    def test_missing_provider_secret_fails_closed(self):
        res = self.client.post(
            "/api/v1/webhooks/executions/alpaca",
            b"{}",
            content_type="application/json",
            HTTP_X_TENANT_REF=TENANT_REF,
        )
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["error"]["code"], "WEBHOOK_AUTHORITY_UNAVAILABLE")
        self.assertFalse(ProviderWebhookInbox.objects.exists())

    def test_tenant_header_is_required(self):
        res = self.client.post("/api/v1/webhooks/executions/alpaca", b"{}", content_type="application/json")
        self.assertEqual(res.status_code, 400)
