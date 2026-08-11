from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from wallet.models import Currency, Transaction, Wallet

TRANSACTIONS_URL = "/api/wallet/transactions/"


class TransactionApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="transactions@example.com", password="testpass123", phone_number="+12025550211"
        )
        self.other = get_user_model().objects.create_user(
            email="other-transactions@example.com", password="testpass123", phone_number="+12025550212"
        )
        currency = Currency.objects.create(name="EUR", symbol="EUR", longer_name="Euro")
        self.wallet = Wallet.objects.create(
            user=self.user, name="Demo", currency=currency, is_real=False
        )
        self.other_wallet = Wallet.objects.create(
            user=self.other, name="Other", currency=currency, is_real=False
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_transaction(self, wallet=None):
        return Transaction.objects.create(
            wallet=wallet or self.wallet,
            type="D",
            amount=Decimal("100.00"),
            status="S",
            gateway="demo",
        )

    def test_auth_required(self):
        response = APIClient().get(TRANSACTIONS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_transactions_are_user_scoped(self):
        own = self.create_transaction()
        self.create_transaction(self.other_wallet)
        response = self.client.get(TRANSACTIONS_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["transaction_id"], str(own.transaction_id))

    def test_retrieve_own_transaction_and_hide_other_users_transaction(self):
        own = self.create_transaction()
        hidden = self.create_transaction(self.other_wallet)
        own_response = self.client.get(f"{TRANSACTIONS_URL}{own.id}/")
        hidden_response = self.client.get(f"{TRANSACTIONS_URL}{hidden.id}/")
        self.assertEqual(own_response.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_transactions_are_read_only(self):
        transaction = self.create_transaction()
        self.assertEqual(self.client.post(TRANSACTIONS_URL, {}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        url = f"{TRANSACTIONS_URL}{transaction.id}/"
        self.assertEqual(self.client.patch(url, {}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.put(url, {}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
