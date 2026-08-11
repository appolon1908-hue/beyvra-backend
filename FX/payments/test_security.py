from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from wallet.models import Currency, Transaction, Wallet


class StripeWebhookSecurityTests(TestCase):
    def test_completed_webhook_is_fail_closed_while_real_money_disabled(self):
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

        self.assertEqual(first.status_code, 503)
        self.assertEqual(second.status_code, 503)
        wallet.refresh_from_db()
        transaction.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("100.00"))
        self.assertEqual(transaction.status, "P")
