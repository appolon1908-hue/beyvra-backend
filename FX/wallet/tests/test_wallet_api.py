from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from wallet.models import Currency, Wallet
from wallet.serializers import WalletListSerializer

WALLETS_URL = "/api/wallet/wallets/"


def create_user(email="wallet@example.com", password="testpass123"):
    phone_suffix = "1" if email.startswith("wallet@") else "2"
    return get_user_model().objects.create_user(
        email=email, password=password, phone_number=f"+1202555020{phone_suffix}"
    )


class WalletApiTests(TestCase):
    def setUp(self):
        self.currency = Currency.objects.create(
            name="USD", symbol="USD", longer_name="US Dollar"
        )

    def test_auth_required(self):
        response = APIClient().get(WALLETS_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wallet_list_is_limited_to_authenticated_user(self):
        user = create_user()
        other = create_user("other-wallet@example.com")
        own = Wallet.objects.create(user=user, name="Own", currency=self.currency, is_real=False)
        Wallet.objects.create(user=other, name="Other", currency=self.currency, is_real=False)
        client = APIClient()
        client.force_authenticate(user)

        response = client.get(WALLETS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], own.id)

    def test_retrieve_own_wallet_and_hide_other_users_wallet(self):
        user = create_user()
        other = create_user("other-wallet@example.com")
        own = Wallet.objects.create(user=user, name="Own", currency=self.currency, is_real=False)
        hidden = Wallet.objects.create(user=other, name="Hidden", currency=self.currency, is_real=False)
        client = APIClient()
        client.force_authenticate(user)

        own_response = client.get(f"{WALLETS_URL}{own.id}/")
        hidden_response = client.get(f"{WALLETS_URL}{hidden.id}/")

        self.assertEqual(own_response.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_wallet_ignores_read_only_balance_and_owner(self):
        user = create_user()
        other = create_user("other-wallet@example.com")
        client = APIClient()
        client.force_authenticate(user)

        response = client.post(
            WALLETS_URL,
            {
                "name": "New demo",
                "currency": self.currency.id,
                "balance": "500.00",
                "user": other.id,
                "is_real": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        wallet = Wallet.objects.get(id=response.data["id"])
        self.assertEqual(wallet.user, user)
        self.assertEqual(wallet.balance, 0)
        self.assertFalse(wallet.is_real)

    def test_list_serialization_matches_current_schema(self):
        user = create_user()
        wallet = Wallet.objects.create(user=user, name="Demo", currency=self.currency, is_real=False)
        client = APIClient()
        client.force_authenticate(user)
        response = client.get(WALLETS_URL)
        self.assertEqual(response.data["results"], WalletListSerializer([wallet], many=True).data)
