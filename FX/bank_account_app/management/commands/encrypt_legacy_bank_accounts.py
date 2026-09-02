from django.core.management.base import BaseCommand
from django.db import transaction

from bank_account_app.models import BankAccount
from integrations.crypto import encrypt, fingerprint


class Command(BaseCommand):
    help = "Encrypt legacy plaintext bank-account numbers in bounded batches."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        batch_size = max(1, min(options["batch_size"], 1000))
        migrated = 0
        while True:
            with transaction.atomic():
                rows = list(
                    BankAccount.objects.select_for_update(skip_locked=True)
                    .filter(account_number__isnull=False, account_number_ciphertext__isnull=True)
                    .exclude(account_number="")[:batch_size]
                )
                if not rows:
                    break
                for row in rows:
                    raw = row.account_number
                    ciphertext, nonce, version = encrypt(raw)
                    row.account_number_ciphertext = ciphertext
                    row.account_number_nonce = nonce
                    row.account_number_key_version = version
                    row.account_number_fingerprint = fingerprint(raw)
                    row.account_number_last_four = raw[-4:]
                    row.account_number = None
                    row.save(update_fields=(
                        "account_number", "account_number_ciphertext", "account_number_nonce",
                        "account_number_key_version", "account_number_fingerprint",
                        "account_number_last_four", "updated_at",
                    ))
                    migrated += 1
        self.stdout.write(f"migrated={migrated}")
