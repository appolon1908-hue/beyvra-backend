from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from bank_account_app.models import BankAccount


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
