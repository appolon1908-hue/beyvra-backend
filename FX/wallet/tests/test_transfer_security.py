from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from wallet.models import Currency, Wallet


class WalletTransferSecurityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="owner@example.com", password="test-pass", phone_number="+12025550101"
        )
        self.attacker = get_user_model().objects.create_user(
            email="attacker@example.com", password="test-pass", phone_number="+12025550102"
        )
        self.recipient = get_user_model().objects.create_user(
            email="recipient@example.com", password="test-pass", phone_number="+12025550103"
        )
        currency = Currency.objects.create(name="USD", symbol="USD", longer_name="US Dollar")
        self.source = Wallet.objects.create(
            user=self.user, name="owner-wallet", currency=currency, balance=Decimal("100.00")
        )
        self.target = Wallet.objects.create(
            user=self.recipient, name="recipient-wallet", currency=currency, balance=Decimal("0.00")
        )
        self.client = APIClient()

    def test_cannot_transfer_from_another_users_wallet(self):
        self.client.force_authenticate(self.attacker)
        response = self.client.post(
            f"/api/wallet/wallets/{self.source.id}/transfer/",
            {"recipient_id": self.target.id, "amount": "10.00"},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(self.source.balance, Decimal("100.00"))
        self.assertEqual(self.target.balance, Decimal("0.00"))

    def test_owner_transfer_updates_both_balances_once(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            f"/api/wallet/wallets/{self.source.id}/transfer/",
            {"recipient_id": self.target.id, "amount": "10.00"},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(self.source.balance, Decimal("90.00"))
        self.assertEqual(self.target.balance, Decimal("10.00"))
