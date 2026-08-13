from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(
    GUEST_DEMO_ENABLED=True,
    PAPER_TRADING_ONLY=True,
    GUEST_DEMO_TTL_SECONDS=300,
)
class GuestDemoSessionSecurityTests(TestCase):
    def test_reused_public_idempotency_key_never_replays_bearer_token(self):
        client = APIClient()
        headers = {"HTTP_IDEMPOTENCY_KEY": "attacker-controlled-key"}

        first = client.post("/api/v1/demo/sessions", {}, format="json", **headers)
        second = client.post("/api/v1/demo/sessions", {}, format="json", **headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.json()["access"], second.json()["access"])
        self.assertEqual(get_user_model().objects.filter(is_guest_demo=True).count(), 2)
