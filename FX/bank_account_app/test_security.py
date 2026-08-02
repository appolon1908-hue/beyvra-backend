from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from bank_account_app.models import BankAccount
from wallet.models import Currency, Wallet


class BankAccountSecurityTests(TestCase):
    def test_user_cannot_delete_another_users_bank_account(self):
        owner = get_user_model().objects.create_user(
            email="bank-owner@example.com", password="test-pass", phone_number="+12025550111"
        )
        attacker = get_user_model().objects.create_user(
            email="bank-attacker@example.com", password="test-pass", phone_number="+12025550112"
        )
        account = BankAccount.objects.create(
            user=owner,
            bank_name="Example Bank",
            account_number="123456789",
            account_holder_name="Owner",
        )
        client = APIClient()
        client.force_authenticate(attacker)

        response = client.delete(
            "/api/bank_account/",
            {"bank_name": account.bank_name, "account_number": account.account_number},
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(BankAccount.objects.filter(pk=account.pk).exists())

    def test_withdrawal_rejects_another_users_wallet(self):
        owner = get_user_model().objects.create_user(
            email="withdraw-owner@example.com", password="test-pass", phone_number="+12025550131"
        )
        attacker = get_user_model().objects.create_user(
            email="withdraw-attacker@example.com", password="test-pass", phone_number="+12025550132"
        )
        currency = Currency.objects.create(name="USD", symbol="USD", longer_name="US Dollar")
        owner_wallet = Wallet.objects.create(user=owner, name="owner-wallet", currency=currency, balance="100.00")
        attacker_bank = BankAccount.objects.create(
            user=attacker, bank_name="Example Bank", account_number="987654321", account_holder_name="Attacker"
        )
        client = APIClient()
        client.force_authenticate(attacker)

        response = client.post(
            "/api/wallet/withdrawal-request/",
            {
                "bank_name": attacker_bank.bank_name,
                "account_number": attacker_bank.account_number,
                "wallet": owner_wallet.id,
                "currency": currency.id,
                "amount": "10.00",
            },
            format="json",
            secure=True,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(attacker.withdrawal_requests.count(), 0)
