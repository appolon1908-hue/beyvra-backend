from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from operations.models import AccountFreeze
from wallet.models import Currency, Transaction, Wallet


class RealWalletFeatureFailClosedTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="real-feature@example.test",
            password="test-pass",
            phone_number="+12025550131",
        )
        self.actor = get_user_model().objects.create_user(
            email="freeze-actor@example.test",
            password="test-pass",
            phone_number="+12025550132",
        )
        self.currency = Currency.objects.create(
            name="Safety Dollar", symbol="SFD", longer_name="Safety Dollar"
        )
        self.demo_wallet = Wallet.objects.create(
            user=self.user,
            name="demo",
            currency=self.currency,
            balance=Decimal("100.00"),
            is_real=False,
        )
        self.real_wallet = Wallet.objects.create(
            user=self.user,
            name="real",
            currency=self.currency,
            balance=Decimal("100.00"),
            is_real=True,
        )
        Transaction.objects.create(
            wallet=self.real_wallet, amount=Decimal("1.00"), type="D", status="P"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("wallet.views.AdyenService")
    def test_deposit_is_disabled_before_provider_construction(self, adapter):
        response = self.client.post(
            f"/api/wallet/wallets/{self.demo_wallet.pk}/deposite/",
            {"amount": "10.00", "currency": "SFD", "gateway": "Adyen"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "FEATURE_DISABLED")
        adapter.assert_not_called()
        self.assertEqual(Transaction.objects.filter(wallet=self.demo_wallet).count(), 0)

    @patch("wallet.views.AdyenService")
    def test_withdrawal_is_disabled_before_provider_construction(self, adapter):
        response = self.client.post(
            f"/api/wallet/wallets/{self.demo_wallet.pk}/withdraw/",
            {"amount": "10.00", "gateway": "Adyen"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "FEATURE_DISABLED")
        adapter.assert_not_called()

    def test_real_wallets_and_transactions_are_hidden_from_customer_reads(self):
        wallets = self.client.get("/api/wallet/wallets/", secure=True).data["results"]
        transactions = self.client.get(
            "/api/wallet/transactions/", secure=True
        ).data["results"]
        self.assertNotIn(str(self.real_wallet.pk), {str(row["id"]) for row in wallets})
        self.assertEqual(transactions, [])
        self.assertEqual(
            self.client.get(
                f"/api/wallet/wallets/{self.real_wallet.pk}/", secure=True
            ).status_code,
            404,
        )

    def test_full_freeze_precedes_feature_disabled_error(self):
        AccountFreeze.objects.create(
            tenant_id="default",
            account=self.user,
            actor=self.actor,
            level="FULL",
            reason_code="ACCOUNT_REVIEW_REQUIRED",
        )
        response = self.client.post(
            f"/api/wallet/wallets/{self.demo_wallet.pk}/withdraw/",
            {"amount": "10.00", "gateway": "Adyen"},
            format="json",
            secure=True,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "ACCOUNT_FROZEN")

    def test_external_broker_order_routes_are_not_registered(self):
        response = self.client.post("/api/orders/", {}, format="json", secure=True)
        self.assertEqual(response.status_code, 404)
