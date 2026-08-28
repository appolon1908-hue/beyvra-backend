import hashlib
import json
import time
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from financial_boundary.webhooks import webhook_signature

SECRET = b"default_super_secret_signing_key_32bytes_minimum!"

SIMULATION = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
    PROVIDER_WEBHOOK_SECRET=SECRET,
)


@SIMULATION
class CanonicalProviderWebhooksApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_ingest_valid_provider_webhook(self):
        now = int(time.time())
        event_id = "evt_alpaca_1001"
        provider = "alpaca"
        body = json.dumps({"event_type": "trade.execution", "order_id": "ord_1001"}).encode("utf-8")
        sig = webhook_signature(
            provider_id=provider,
            event_id=event_id,
            timestamp=now,
            raw_body=body,
            secret=SECRET
        )

        headers = {
            "HTTP_X_PROVIDER_ID": provider,
            "HTTP_X_EVENT_ID": event_id,
            "HTTP_X_TIMESTAMP": str(now),
            "HTTP_X_SIGNATURE": sig,
            "CONTENT_TYPE": "application/json"
        }

        res = self.client.post(f"/api/v1/webhooks/executions/{provider}", body, **headers)
        self.assertEqual(res.status_code, 202)
        self.assertEqual(res.json()["status"], "accepted")

        # Duplicate submission
        res_dup = self.client.post(f"/api/v1/webhooks/executions/{provider}", body, **headers)
        self.assertEqual(res_dup.status_code, 200)
        self.assertEqual(res_dup.json()["status"], "duplicate")

    def test_ingest_disallowed_provider(self):
        res = self.client.post("/api/v1/webhooks/executions/untrusted_broker", b"{}")
        self.assertEqual(res.status_code, 403)
