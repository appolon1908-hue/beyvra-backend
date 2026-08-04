from django.test import TestCase
from unittest.mock import patch
from rest_framework.test import APIClient

from integrations.models import Organization, OrganizationMembership
from real_wallet.models import Asset, LedgerAccount, RealWallet
from real_wallet.services import post_transaction
from users.models import User


class RealWalletBoundaryTests(TestCase):
    def setUp(self):
        with patch("users.signals.async_send_welcome_email.delay"):
            self.user = User.objects.create_user(
                email="real-wallet@example.com", password="pass12345", phone_number="+12025550999"
            )
        self.org = Organization.objects.create(name="Real wallet test tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.org)
        self.asset = Asset.objects.create(symbol="TST", name="Test Asset", decimals=6)
        self.debit = LedgerAccount.objects.create(
            tenant=self.org, owner_type="PLATFORM", asset=self.asset,
            account_code="DEPOSIT_CLEARING", account_type="CLEARING", normal_side="DEBIT"
        )
        self.credit = LedgerAccount.objects.create(
            tenant=self.org, owner_type="CUSTOMER", asset=self.asset,
            account_code="CUSTOMER_AVAILABLE", account_type="LIABILITY", normal_side="CREDIT"
        )

    def test_real_wallet_routes_are_disabled_without_demo_fallback(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/v1/wallets/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "FEATURE_DISABLED")

    def test_balanced_ledger_is_idempotent(self):
        kwargs = {
            "tenant": self.org, "transaction_type": "TEST", "idempotency_key": "ledger-test-1",
            "entries": [
                {"account": self.debit, "asset": self.asset, "direction": "DEBIT", "amount_atomic": "100"},
                {"account": self.credit, "asset": self.asset, "direction": "CREDIT", "amount_atomic": "100"},
            ],
        }
        first = post_transaction(**kwargs)
        second = post_transaction(**kwargs)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.entries.count(), 2)

    def test_unbalanced_ledger_is_rejected(self):
        with self.assertRaises(ValueError):
            post_transaction(
                tenant=self.org, transaction_type="TEST", idempotency_key="unbalanced",
                entries=[{"account": self.debit, "asset": self.asset, "direction": "DEBIT", "amount_atomic": "1"}],
            )

    def test_real_wallet_has_no_demo_wallet_foreign_key(self):
        field_models = {field.related_model for field in RealWallet._meta.fields if field.is_relation}
        self.assertNotIn("wallet.Wallet", {model._meta.label for model in field_models})

    def test_large_atomic_amount_is_supported_without_float(self):
        amount = "9" * 60
        tx = post_transaction(
            tenant=self.org,
            transaction_type="LARGE_AMOUNT",
            idempotency_key="large-amount",
            entries=[
                {"account": self.debit, "asset": self.asset, "direction": "DEBIT", "amount_atomic": amount},
                {"account": self.credit, "asset": self.asset, "direction": "CREDIT", "amount_atomic": amount},
            ],
        )
        self.assertEqual(tx.entries.count(), 2)
        self.assertEqual(tx.entries.first().amount_atomic.as_tuple().exponent, 0)
