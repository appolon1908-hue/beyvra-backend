from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from bank_account_app.models import BankAccount
from bank_account_app.models import WithdrawalRequest
from wallet.models import Currency, Wallet
from integrations.models import Organization, OrganizationMembership
from apps.foundation.models import ApplicationAuditEvent
from django.core.management import call_command
from integrations.crypto import decrypt


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
            {"bank_account_id": account.pk},
            format="json",
            secure=True,
            HTTP_IDEMPOTENCY_KEY="cross-tenant-delete",
            HTTP_X_REQUEST_ID="4268bb29-93a8-42c4-820f-aa27e7bd1001",
            HTTP_IF_MATCH=account.updated_at.isoformat().replace("+00:00", "Z"),
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

        # Legacy wallet withdrawals are deliberately retired: callers receive
        # no writable compatibility surface and no request is created.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(attacker.withdrawal_requests.count(), 0)


@override_settings(
    DATA_ENCRYPTION_KEY="bank-account-test-key",
    API_TOKEN_PEPPER="bank-account-fingerprint-test-pepper",
)
class BankAccountCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="bank-command@example.test", password="test-pass", phone_number="+12025550151",
        )
        organization = Organization.objects.create(name="Bank command tenant")
        OrganizationMembership.objects.create(user=self.user, organization=organization, role="member")
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.headers = {
            "HTTP_IDEMPOTENCY_KEY": "bank-create-test",
            "HTTP_X_REQUEST_ID": "4268bb29-93a8-42c4-820f-aa27e7bd1002",
        }

    def test_create_is_encrypted_masked_idempotent_and_audited(self):
        payload = {
            "bank_name": "Example Bank", "account_number": "123456789",
            "account_holder_name": "Test Holder", "routing_number": "021000021",
            "swift_code": "EXAMPL22", "iban": "GB82WEST12345698765432",
        }
        first = self.client.post("/api/bank_account/", payload, format="json", **self.headers)
        replay = self.client.post("/api/bank_account/", payload, format="json", **self.headers)
        conflict = self.client.post("/api/bank_account/", {**payload, "account_number": "987654321"}, format="json", **self.headers)
        self.assertEqual(first.status_code, 201); self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json(), first.json()); self.assertEqual(conflict.status_code, 409)
        row = BankAccount.objects.get(user=self.user)
        self.assertIsNone(row.account_number); self.assertTrue(row.account_number_ciphertext)
        self.assertNotEqual(row.account_number_fingerprint, __import__('hashlib').sha256(b"123456789").hexdigest()[:32])
        for field in ("routing_number", "swift_code", "iban"):
            self.assertIsNone(getattr(row, field))
            self.assertTrue(getattr(row, f"{field}_ciphertext"))
        self.assertEqual(first.json()["data"]["account_number"], "****6789")
        self.assertEqual(first.json()["data"]["routing_number"], "****0021")
        self.assertEqual(first.json()["data"]["swift_code"], "****PL22")
        self.assertEqual(first.json()["data"]["iban"], "****5432")
        self.assertNotIn("123456789", str(first.json()))
        self.assertNotIn("021000021", str(first.json()))
        self.assertNotIn("EXAMPL22", str(first.json()))
        self.assertNotIn("GB82WEST12345698765432", str(first.json()))
        self.assertEqual(ApplicationAuditEvent.objects.filter(action="bank_account.create").count(), 1)

    def test_bank_account_create_cannot_smuggle_withdrawal(self):
        payload = {
            "bank_name": "Example Bank", "account_number": "123456780",
            "account_holder_name": "Test Holder",
            "withdrawal_request": {"amount": "10.00", "currency": 1},
        }
        response = self.client.post(
            "/api/bank_account/", payload, format="json",
            HTTP_IDEMPOTENCY_KEY="nested-withdrawal-test",
            HTTP_X_REQUEST_ID="4268bb29-93a8-42c4-820f-aa27e7bd1004",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_delete_retires_instead_of_deleting(self):
        row = BankAccount.objects.create(
            user=self.user, bank_name="Example Bank", account_number=None,
            account_number_last_four="6789", account_holder_name="Test Holder",
        )
        headers = {
            "HTTP_IDEMPOTENCY_KEY": "bank-retire-test",
            "HTTP_X_REQUEST_ID": "4268bb29-93a8-42c4-820f-aa27e7bd1003",
            "HTTP_IF_MATCH": row.updated_at.isoformat().replace("+00:00", "Z"),
        }
        response = self.client.delete("/api/bank_account/", {"bank_account_id": row.pk}, format="json", **headers)
        replay = self.client.delete("/api/bank_account/", {"bank_account_id": row.pk}, format="json", **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), response.json())
        row.refresh_from_db(); self.assertFalse(row.is_active); self.assertIsNotNone(row.revoked_at)

    def test_legacy_plaintext_backfill_encrypts_and_clears_source(self):
        row = BankAccount.objects.create(
            user=self.user, bank_name="Legacy Bank", account_number="246813579",
            routing_number="021000021", swift_code="EXAMPL22",
            iban="GB82WEST12345698765432",
            account_holder_name="Legacy Holder",
        )
        call_command("encrypt_legacy_bank_accounts", batch_size=10)
        row.refresh_from_db()
        self.assertIsNone(row.account_number)
        self.assertEqual(row.account_number_last_four, "3579")
        self.assertEqual(
            decrypt(row.account_number_ciphertext, row.account_number_nonce, key_version=row.account_number_key_version),
            "246813579",
        )
        for field, expected in (
            ("routing_number", "021000021"),
            ("swift_code", "EXAMPL22"),
            ("iban", "GB82WEST12345698765432"),
        ):
            self.assertIsNone(getattr(row, field))
            self.assertEqual(
                decrypt(
                    getattr(row, f"{field}_ciphertext"),
                    getattr(row, f"{field}_nonce"),
                    key_version=getattr(row, f"{field}_key_version"),
                ),
                expected,
            )
