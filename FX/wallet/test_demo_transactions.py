from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from wallet.models import Currency, Transaction, Wallet


@override_settings(PAPER_TRADING_ONLY=True, SIMULATED_TRADING_ENABLED=True)
class DemoTransactionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="demo-funds@example.com", password="test-pass", phone_number="+12025550131"
        )
        self.currency = Currency.objects.create(name="USD", symbol="USD", longer_name="US Dollar")
        self.wallet = Wallet.objects.create(
            user=self.user,
            name="demo-wallet",
            currency=self.currency,
            balance=Decimal("100.00"),
            is_real=False,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_demo_deposit_credits_wallet_and_records_success(self):
        response = self.client.post(
            f"/api/wallet/wallets/{self.wallet.id}/deposit/",
            {"amount": "25.00", "currency": "USD", "gateway": "demo"},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("125.00"))
        self.assertTrue(
            Transaction.objects.filter(wallet=self.wallet, type="D", status="S", amount=25).exists()
        )

    def test_demo_withdrawal_debits_wallet_and_records_success(self):
        response = self.client.post(
            f"/api/wallet/wallets/{self.wallet.id}/withdraw/",
            {"amount": 25, "gateway": "demo"},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("75.00"))
        self.assertTrue(
            Transaction.objects.filter(wallet=self.wallet, type="W", status="S", amount=25).exists()
        )

    def test_real_wallet_rejects_staging_deposit(self):
        real_wallet = Wallet.objects.create(
            user=self.user,
            name="real-wallet",
            currency=self.currency,
            balance=Decimal("100.00"),
            is_real=True,
        )
        response = self.client.post(
            f"/api/wallet/wallets/{real_wallet.id}/deposit/",
            {"amount": "25.00", "currency": "USD", "gateway": "demo"},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["code"], "FEATURE_DISABLED")
        real_wallet.refresh_from_db()
        self.assertEqual(real_wallet.balance, Decimal("100.00"))
