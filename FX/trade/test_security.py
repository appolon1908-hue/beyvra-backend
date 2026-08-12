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

    def test_legacy_trade_create_is_not_a_writable_authority(self):
        client, wallet, payload = self._trade_fixture()

        first = client.post(
            "/api/trades/", payload, format="json", secure=True,
            HTTP_IDEMPOTENCY_KEY="same-request"
        )
        second = client.post(
            "/api/trades/", payload, format="json", secure=True,
            HTTP_IDEMPOTENCY_KEY="same-request"
        )

        self.assertEqual(first.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(second.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("100.00"))

    def test_legacy_trade_cancel_route_is_removed(self):
        client, wallet, payload = self._trade_fixture()
        created = client.post("/api/trades/", payload, format="json", secure=True)

        self.assertEqual(created.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        cancelled = client.post("/api/trades/1/cancel/", secure=True)
        self.assertEqual(cancelled.status_code, status.HTTP_404_NOT_FOUND)
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

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
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

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("100.00"))
