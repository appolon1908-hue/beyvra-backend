from django.test import TestCase
from rest_framework.test import APIClient

from apps.trading.models import TradingOrder
from users.models import User


class OperatorPlatformApiTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            email="operator-platform@example.test",
            password="safe-password",
            is_staff=True,
            is_mfa_enabled=True,
            two_factor_authentication_enabled=True,
        )
        self.password_only = User.objects.create_user(
            email="password-only-operator@example.test",
            password="safe-password",
            is_staff=True,
        )
        TradingOrder.objects.create(
            tenant_ref="default",
            subject_ref="fixture-subject",
            account_ref="sim:fixture",
            instrument_id="BTC-USD",
            order_type="MARKET",
            side="BUY",
            quantity="1",
        )

    def test_current_mfa_is_required(self):
        client = APIClient()
        client.force_authenticate(self.password_only)
        self.assertEqual(client.get("/api/v1/operator/orders").status_code, 403)

        client.force_authenticate(
            self.operator,
            token={
                "auth_strength": "PASSWORD",
                "mfa_verified_at": 1,
                "session_id": "password-session",
            },
        )
        self.assertEqual(client.get("/api/v1/operator/orders").status_code, 403)

        client.force_authenticate(
            self.operator,
            token={
                "auth_strength": "MFA",
                "mfa_verified_at": 1,
                "session_id": "mfa-session",
            },
        )
        self.assertEqual(client.get("/api/v1/operator/orders").status_code, 200)

    def test_operator_read_models_are_safe_and_bounded(self):
        client = APIClient()
        client.force_authenticate(self.operator)
        orders = client.get("/api/v1/operator/orders")
        self.assertEqual(orders.status_code, 200)
        self.assertEqual(orders.json()["limit"], 200)
        self.assertTrue(orders.json()["results"][0]["simulation"])

        providers = client.get("/api/v1/operator/providers/health")
        self.assertEqual(providers.status_code, 200)
        breaks = client.get("/api/v1/operator/reconciliation/breaks")
        self.assertFalse(breaks.json()["resolution_mutation_enabled"])
