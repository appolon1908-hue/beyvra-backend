from django.contrib.auth import get_user_model
from django.test import TestCase
from uuid import uuid4
from rest_framework import status
from rest_framework.test import APIClient

from ..models import Currency, Wallet
from ..serializers import WalletListSerializer

WALLETS_URL = "/api/wallet/wallets/"


def create_user(email="user@example.come", password="testpass123"):
    """Create and return user."""
    phone_number = f"+1{uuid4().int % 10**10:010d}"
    return get_user_model().objects.create_user(
        email=email, password=password, phone_number=phone_number
    )


def create_currency(symbol="USD", name="US dollar"):
    return Currency.objects.create(
        symbol=symbol, name=name, longer_name=f"{name} currency"
    )


def detail_url(id):
    return f"{WALLETS_URL}{id}/"


class PublicWalletsApiTests(TestCase):
    """Test unauthenticated API requests."""

    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        """Test auth is requited for retrieving wallets."""
        res = self.client.get(WALLETS_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateWalletsApiTests(TestCase):
    """Test unauthenticated API requests."""

    def setUp(self):
        self.user = create_user()
        self.currency = create_currency()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_retrieve_wallets(self):
        """Test retrieving a list of wallets."""
        Wallet.objects.create(user=self.user, name="primary", currency=self.currency)

        res = self.client.get(WALLETS_URL)

        wallets = Wallet.objects.all().order_by("-created_at")
        serializer = WalletListSerializer(wallets, many=True)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["results"], serializer.data)

    def test_wallets_limited_to_user(self):
        """Test list of wallets is limited to authenticated user."""
        user2 = create_user(email="user2@example.com")
        Wallet.objects.create(user=user2, name="other", currency=self.currency)
        wallet = Wallet.objects.create(
            user=self.user, name="primary", currency=self.currency
        )

        res = self.client.get(WALLETS_URL)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(str(res.data["results"][0]["user"]), str(self.user.id))
        self.assertEqual(str(res.data["results"][0]["id"]), str(wallet.id))

    def test_get_wallet_details(self):
        """Test retrieving a wallet details."""
        wallet = Wallet.objects.create(
            user=self.user, name="primary", currency=self.currency
        )

        url = detail_url(str(wallet.id))
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(str(res.data["user"]["id"]), str(self.user.id))
        self.assertEqual(str(res.data["id"]), str(wallet.id))

    def test_get_other_users_wallet_details_fails(self):
        """Test retrieving a wallet details."""
        Wallet.objects.create(user=self.user, name="primary", currency=self.currency)

        user2 = create_user(email="user2@example.com")
        wallet2 = Wallet.objects.create(
            user=user2, name="other", currency=self.currency
        )

        url = detail_url(str(wallet2.id))
        res = self.client.get(url)

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_wallet(self):
        """Test creating a wallet."""
        payload = {"name": "primary", "currency": self.currency.id}
        res = self.client.post(WALLETS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(res.data["user"]), str(self.user.id))
        self.assertEqual(str(res.data["currency"]), str(self.currency.id))

    def test_create_wallet_with_same_name_fails(self):
        """Wallet names are unique per user."""
        Wallet.objects.create(user=self.user, name="primary", currency=self.currency)

        payload = {"name": "primary", "currency": self.currency.id}
        res = self.client.post(WALLETS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_wallet_with_unknown_currency_fails(self):
        payload = {"name": "primary", "currency": 999999}
        res = self.client.post(WALLETS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wallet_creation_with_read_only_fields(self):
        """Test creating a wallet with"""
        user2 = create_user(email="user2@gmail.com")
        payload = {
            "name": "primary",
            "currency": self.currency.id,
            "balance": 100.0,
            "user": str(user2.id),
            "is_real": True,
        }
        res = self.client.post(WALLETS_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(res.data["balance"], 100)
        self.assertNotEqual(res.data["user"], user2.id)
        self.assertEqual(res.data["balance"], "0.00")
        self.assertFalse(res.data["is_real"])
        self.assertEqual(str(res.data["user"]), str(self.user.id))

    def test_update_wallet_name_is_owner_scoped(self):
        wallet = Wallet.objects.create(
            user=self.user, name="primary", currency=self.currency
        )
        payload = {"name": "renamed"}

        url = detail_url(wallet.id)
        res = self.client.patch(url, payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        wallet.refresh_from_db()
        self.assertEqual(wallet.name, "renamed")

    def test_delete_wallet_not_permitted(self):
        """Test deleting a wallet."""
        wallet = Wallet.objects.create(
            user=self.user, name="primary", currency=self.currency
        )

        url = detail_url(str(wallet.id))
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
