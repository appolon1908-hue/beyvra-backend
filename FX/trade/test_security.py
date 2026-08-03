from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from trade.models import Asset, AssetType, TradeCategory
from wallet.models import Currency, Wallet


class TradeSecurityTests(TestCase):
    def _trade_fixture(self):
        user = get_user_model().objects.create_user(
            email="trade-demo@example.com", password="test-pass", phone_number="+12025550130"
        )
        currency = Currency.objects.create(name="GBP", symbol="GBP", longer_name="British Pound")
        wallet = Wallet.objects.create(
            user=user,
            name="demo-wallet",
            currency=currency,
            balance=Decimal("100.00"),
            is_real=False,
        )
        asset_type, _ = AssetType.objects.get_or_create(name="Stock")
        asset = Asset.objects.create(name="Test Equity", symbol="TST", asset_type=asset_type)
        category, _ = TradeCategory.objects.get_or_create(name="market")
        client = APIClient()
        client.force_authenticate(user)
        payload = {
            "wallet": wallet.id,
            "asset": asset.id,
            "quantity": "1.0",
            "price_per_unit": "10.0000",
            "trade_type": "buy",
            "category": category.name,
            "duration": 1,
        }
        return client, wallet, payload

    def test_idempotency_key_prevents_duplicate_trade(self):
        client, wallet, payload = self._trade_fixture()

        first = client.post(
            "/api/trades/", payload, format="json", secure=True,
            HTTP_IDEMPOTENCY_KEY="same-request"
        )
        second = client.post(
            "/api/trades/", payload, format="json", secure=True,
            HTTP_IDEMPOTENCY_KEY="same-request"
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data["id"], second.data["id"])
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("90.00"))

    def test_cancel_active_trade_refunds_wallet_once(self):
        client, wallet, payload = self._trade_fixture()
        created = client.post("/api/trades/", payload, format="json", secure=True)

        cancelled = client.post(f"/api/trades/{created.data['id']}/cancel/", secure=True)
        repeated = client.post(f"/api/trades/{created.data['id']}/cancel/", secure=True)

        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated.status_code, status.HTTP_409_CONFLICT)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("100.00"))

    def test_staging_rejects_real_money_wallet(self):
        user = get_user_model().objects.create_user(
            email="real-wallet@example.com", password="test-pass", phone_number="+12025550123"
        )
        currency = Currency.objects.create(name="EUR", symbol="EUR", longer_name="Euro")
        wallet = Wallet.objects.create(
            user=user, name="real-wallet", currency=currency, balance=Decimal("100.00"), is_real=True
        )
        asset_type, _ = AssetType.objects.get_or_create(name="Forex")
        asset, _ = Asset.objects.get_or_create(
            symbol="EURUSD", defaults={"name": "Euro Dollar", "asset_type": asset_type}
        )
        category, _ = TradeCategory.objects.get_or_create(name="market")
        client = APIClient()
        client.force_authenticate(user)

        response = client.post(
            "/api/trades/",
            {
                "wallet": wallet.id,
                "asset": asset.id,
                "quantity": "1.0",
                "price_per_unit": "10.0000",
                "trade_type": "buy",
                "category": category.name,
                "duration": 1,
            },
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Real-money trading is disabled", str(response.data))
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("100.00"))

    def test_user_cannot_trade_with_another_users_wallet(self):
        owner = get_user_model().objects.create_user(
            email="trade-owner@example.com", password="test-pass", phone_number="+12025550121"
        )
        attacker = get_user_model().objects.create_user(
            email="trade-attacker@example.com", password="test-pass", phone_number="+12025550122"
        )
        currency = Currency.objects.create(name="USD", symbol="USD", longer_name="US Dollar")
        wallet = Wallet.objects.create(
            user=owner, name="owner-wallet", currency=currency, balance=Decimal("100.00")
        )
        asset_type, _ = AssetType.objects.get_or_create(name="Stock")
        asset = Asset.objects.create(name="Example", symbol="EX", asset_type=asset_type)
        category, _ = TradeCategory.objects.get_or_create(name="market")
        client = APIClient()
        client.force_authenticate(attacker)

        response = client.post(
            "/api/trades/",
            {
                "wallet": wallet.id,
                "asset": asset.id,
                "quantity": "1.0",
                "price_per_unit": "10.0000",
                "trade_type": "buy",
                "category": category.name,
                "duration": 1,
            },
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("100.00"))
