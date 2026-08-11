from django.contrib.auth import get_user_model
from django.test import TestCase
from uuid import uuid4
from rest_framework import status
from rest_framework.test import APIClient

from ..models import Currency, Transaction, Wallet
from ..serializers import TransactionSerializer

TRANSACTIONS_URL = "/api/wallet/transactions/"


def create_user(email="user@example.come", password="testpass123"):
    """Create and return user."""
    phone_number = f"+1{uuid4().int % 10**10:010d}"
    return get_user_model().objects.create_user(
        email=email, password=password, phone_number=phone_number
    )


def create_transaction(
    wallet,
    type="D",
    amount=100,
    status="P",
    gateway="test",
    reference="tracking-id-1234",
):
    """Create and return transaction."""
    return Transaction.objects.create(
        wallet=wallet,
        type=type,
        amount=amount,
        status=status,
        gateway=gateway,
        reference=reference,
    )


def detail_url(id):
    return f"{TRANSACTIONS_URL}{id}/"


class PublicTransactionsApiTests(TestCase):
    """Test unauthenticated API requests."""

    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        """Test auth is requited for retrieving transactions."""
        res = self.client.get(TRANSACTIONS_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateTransactionsApiTests(TestCase):
    """Test unauthenticated API requests."""

    def setUp(self):
        self.user = create_user()
        self.currency = Currency.objects.create(
            name="Test Dollar", symbol="TST", longer_name="Test Dollar Currency"
        )
        self.wallet = Wallet.objects.create(
            user=self.user, name="primary", currency=self.currency, is_real=False
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_retrieve_transactions(self):
        """Test retrieving a list of transactions."""
        create_transaction(self.wallet)
        res = self.client.get(TRANSACTIONS_URL)

        transactions = Transaction.objects.all().order_by("-created_at")
        serializer = TransactionSerializer(transactions, many=True)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["results"], serializer.data)

    def test_transactions_limited_to_user(self):
        """Test list of transactions is limited to authenticated user."""
        user2 = create_user(email="user2@example.com")
        user2_wallet = Wallet.objects.create(
            user=user2, name="other", currency=self.currency, is_real=False
        )

        transaction_1 = create_transaction(self.wallet)
        create_transaction(user2_wallet)

        res = self.client.get(TRANSACTIONS_URL)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(
            str(res.data["results"][0]["wallet"]["id"]), str(self.wallet.id)
        )
        self.assertEqual(str(res.data["results"][0]["id"]), str(transaction_1.id))

    def test_get_transaction_details(self):
        """Test retrieving a transaction details."""
        transaction = create_transaction(self.wallet)

        url = detail_url(transaction.id)
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(str(res.data["wallet"]["id"]), str(self.wallet.id))
        self.assertEqual(str(res.data["id"]), str(transaction.id))

    def test_get_other_users_transaction_details_fails(self):
        """Test retrieving a wallet details."""
        user2 = create_user(email="user2@example.com")
        user2_wallet = Wallet.objects.create(
            user=user2, name="other", currency=self.currency, is_real=False
        )
        transaction2 = create_transaction(user2_wallet)

        url = detail_url(transaction2.id)
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_transaction_not_permitetd(self):
        """Test creating a transaction is not allowed."""
        payload = {}
        res = self.client.post(TRANSACTIONS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_update_transaction_not_permitetd(self):
        """Test updating an transaction is not allowed."""
        transaction = create_transaction(self.wallet)
        payload = {}
        url = detail_url(str(transaction.id))
        res = self.client.patch(url, payload)
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        res = self.client.put(url, payload)
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_transaction_not_permitted(self):
        """Test deleting a transaction is not allowed."""
        transaction = create_transaction(self.wallet)
        url = detail_url(str(transaction.id))
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
