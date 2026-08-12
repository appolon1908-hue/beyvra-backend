from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from wallet.models import Currency, Transaction, Wallet
from payments.models import PaymentMethod


class StripeWebhookSecurityTests(TestCase):
    def test_completed_webhook_is_idempotent(self):
        user = get_user_model().objects.create_user(
            email="stripe@example.com", password="test-pass", phone_number="+12025550141"
        )
        currency = Currency.objects.create(name="USD", symbol="USD", longer_name="US Dollar")
        wallet = Wallet.objects.create(user=user, name="primary", currency=currency, balance=Decimal("100.00"))
        transaction = Transaction.objects.create(
            wallet=wallet,
            type="D",
            amount=Decimal("25.00"),
            status="P",
            reference="cs_rehearsal_123",
        )
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"id": transaction.reference}},
        }
        client = APIClient()

        with patch("payments.views.stripe.Webhook.construct_event", return_value=event):
            first = client.post(
                "/api/payment/stripe_webhook/", b"{}", content_type="application/json",
                HTTP_STRIPE_SIGNATURE="test", secure=True,
            )
            second = client.post(
                "/api/payment/stripe_webhook/", b"{}", content_type="application/json",
                HTTP_STRIPE_SIGNATURE="test", secure=True,
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        wallet.refresh_from_db()
        transaction.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("125.00"))
        self.assertEqual(transaction.status, "S")


class WalletTransferSecurityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="transfer@example.com", password="test-pass", phone_number="+12025550142"
        )
        currency = Currency.objects.create(name="EUR", symbol="EUR", longer_name="Euro")
        self.source = Wallet.objects.create(
            user=self.user, name="source", currency=currency, balance=Decimal("100.00"), is_real=False
        )
        self.target = Wallet.objects.create(
            user=self.user, name="target", currency=currency, balance=Decimal("25.00"), is_real=False
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_negative_transfer_is_rejected_without_changing_balances(self):
        response = self.client.post(
            "/api/payment/wallet/transfer/",
            {"source_wallet_id": self.source.id, "target_wallet_id": self.target.id, "amount": "-10.00"},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, 400)
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(self.source.balance, Decimal("100.00"))
        self.assertEqual(self.target.balance, Decimal("25.00"))

    def test_transfer_updates_both_demo_wallets_atomically(self):
        response = self.client.post(
            "/api/payment/wallet/transfer/",
            {"source_wallet_id": self.source.id, "target_wallet_id": self.target.id, "amount": "10.00"},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(self.source.balance, Decimal("90.00"))
        self.assertEqual(self.target.balance, Decimal("35.00"))


class PaymentProcessingContractTests(TestCase):
    def test_payment_method_id_is_validated_instead_of_raising_key_error(self):
        user = get_user_model().objects.create_user(
            email="processing@example.com", password="test-pass", phone_number="+12025550143"
        )
        currency = Currency.objects.create(name="GBP", symbol="GBP", longer_name="Pound Sterling")
        wallet = Wallet.objects.create(
            user=user, name="processing", currency=currency, balance=Decimal("0"), is_real=False
        )
        method = PaymentMethod.objects.create(name="Contract card", type="credit_card")
        client = APIClient()
        client.force_authenticate(user)

        response = client.post(
            "/api/payment/process_payment/",
            {"wallet_id": wallet.id, "payment_method_id": method.id, "amount": "5.00"},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "Credit card payment processed")
