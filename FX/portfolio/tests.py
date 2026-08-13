from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from portfolio.models import Asset, AssetBalance, AssetProfitLoss, AssetType
from wallet.models import Currency, Wallet


class PortfolioSummaryTests(TestCase):
    def test_summary_is_authenticated_and_user_scoped(self):
        user = get_user_model().objects.create_user(
            email="portfolio@example.com", password="test-pass", phone_number="+12025550132"
        )
        currency = Currency.objects.create(name="CAD", symbol="CAD", longer_name="Canadian Dollar")
        Wallet.objects.create(
            user=user, name="demo", currency=currency, balance=Decimal("200.00"), is_real=False
        )
        asset_type = AssetType.objects.create(name="Equity")
        asset = Asset.objects.create(
            user=user,
            name="Example Holding",
            number_of_shares=2,
            initial_price=10,
            current_price=15,
            asset_type=asset_type,
        )
        AssetBalance.objects.create(asset=asset, current_balance=30)
        AssetProfitLoss.objects.create(asset=asset)

        anonymous = APIClient().get("/api/portfolio/summary/", secure=True)
        client = APIClient()
        client.force_authenticate(user)
        response = client.get("/api/portfolio/summary/", secure=True)

        self.assertEqual(anonymous.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["cash_balance"], 200.0)
        self.assertEqual(response.data["invested_balance"], 30.0)
        self.assertEqual(response.data["total_balance"], 230.0)
        self.assertEqual(response.data["profit_loss"], 10.0)
        self.assertEqual(response.data["holdings"][0]["name"], "Example Holding")
