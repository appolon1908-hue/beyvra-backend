from django.core.management.base import BaseCommand
from django.db import models, transaction

from bank_account_app.models import BankAccount
from integrations.crypto import encrypt, fingerprint


class Command(BaseCommand):
    help = "Encrypt legacy plaintext bank-account identifiers in bounded batches."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        batch_size = max(1, min(options["batch_size"], 1000))
        migrated = 0
        while True:
            with transaction.atomic():
                rows = list(
                    BankAccount.objects.select_for_update(skip_locked=True)
                    .filter(
                        (models.Q(account_number__isnull=False, account_number_ciphertext__isnull=True) & ~models.Q(account_number=""))
                        | (models.Q(routing_number__isnull=False, routing_number_ciphertext__isnull=True) & ~models.Q(routing_number=""))
                        | (models.Q(swift_code__isnull=False, swift_code_ciphertext__isnull=True) & ~models.Q(swift_code=""))
                        | (models.Q(iban__isnull=False, iban_ciphertext__isnull=True) & ~models.Q(iban=""))
                    )[:batch_size]
                )
                if not rows:
                    break
                for row in rows:
                    update_fields = ["updated_at"]
                    for field in ("account_number", "routing_number", "swift_code", "iban"):
                        raw = getattr(row, field)
                        if not raw or getattr(row, f"{field}_ciphertext"):
                            continue
                        ciphertext, nonce, version = encrypt(raw)
                        setattr(row, f"{field}_ciphertext", ciphertext)
                        setattr(row, f"{field}_nonce", nonce)
                        setattr(row, f"{field}_key_version", version)
                        setattr(row, f"{field}_last_four", raw[-4:])
                        setattr(row, field, None)
                        update_fields.extend((
                            field, f"{field}_ciphertext", f"{field}_nonce",
                            f"{field}_key_version", f"{field}_last_four",
                        ))
                        if field == "account_number":
                            row.account_number_fingerprint = fingerprint(raw)
                            update_fields.append("account_number_fingerprint")
                    row.save(update_fields=update_fields)
                    migrated += 1
        self.stdout.write(f"migrated={migrated}")
