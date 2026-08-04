import hashlib
import json
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import AssetBalance, BalanceHold, FeatureFlag, LedgerEntry, LedgerTransaction

REAL_FEATURE_FLAGS = (
    "real_wallet_read_enabled",
    "real_wallet_deposits_enabled",
    "real_wallet_withdrawals_enabled",
    "real_wallet_internal_transfers_enabled",
    "real_trading_enabled",
    "external_execution_enabled",
    "internal_execution_enabled",
)


class RealWalletFeatureDisabled(Exception):
    code = "FEATURE_DISABLED"


def is_feature_enabled(key: str) -> bool:
    return FeatureFlag.objects.filter(key=key, enabled=True).exists()


def canonical_request_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def post_transaction(*, tenant, transaction_type, idempotency_key, entries, metadata=None, correlation_id=None):
    """Post one balanced, single-asset immutable ledger transaction."""
    if not entries:
        raise ValueError("ledger transaction requires entries")
    totals = {}
    for item in entries:
        amount = Decimal(str(item["amount_atomic"]))
        if amount <= 0:
            raise ValueError("ledger amounts must be positive")
        if item["direction"] not in {"DEBIT", "CREDIT"}:
            raise ValueError("invalid ledger direction")
        totals.setdefault(item["asset"].pk, {"DEBIT": Decimal(0), "CREDIT": Decimal(0)})[item["direction"]] += amount
    if len(totals) != 1:
        raise ValueError("ledger transaction cannot mix assets")
    total = next(iter(totals.values()))
    if total["DEBIT"] != total["CREDIT"]:
        raise ValueError("ledger transaction is unbalanced")
    now = timezone.now()
    with transaction.atomic():
        existing = LedgerTransaction.objects.select_for_update().filter(tenant=tenant, idempotency_key=idempotency_key).first()
        if existing:
            return existing
        ledger_tx = LedgerTransaction.objects.create(
            tenant=tenant, transaction_type=transaction_type, idempotency_key=idempotency_key,
            status="POSTED", effective_at=now, posted_at=now, correlation_id=correlation_id, metadata=metadata or {},
        )
        LedgerEntry.objects.bulk_create([
            LedgerEntry(transaction=ledger_tx, account=item["account"], asset=item["asset"], direction=item["direction"], amount_atomic=Decimal(str(item["amount_atomic"])))
            for item in entries
        ])
        return ledger_tx


@transaction.atomic
def create_hold(*, tenant, wallet, asset_network, amount_atomic, reason, idempotency_key, reference_id=None, expires_at=None):
    amount = Decimal(str(amount_atomic))
    if amount <= 0:
        raise ValueError("hold amount must be positive")
    existing = BalanceHold.objects.select_for_update().filter(tenant=tenant, idempotency_key=idempotency_key).first()
    if existing:
        return existing
    balance = AssetBalance.objects.select_for_update().get(wallet=wallet, asset_network=asset_network)
    if balance.available_atomic < amount:
        raise ValueError("insufficient available balance")
    balance.held_atomic += amount
    balance.save(update_fields=["held_atomic", "updated_at"])
    return BalanceHold.objects.create(
        tenant=tenant, wallet=wallet, asset_network=asset_network, amount_atomic=amount,
        reason=reason, idempotency_key=idempotency_key, reference_id=reference_id, expires_at=expires_at,
    )


def _transition_hold(hold_id, target):
    with transaction.atomic():
        hold = BalanceHold.objects.select_for_update().select_related("wallet").get(pk=hold_id)
        if hold.state != "ACTIVE":
            raise ValueError("hold is not active")
        balance = AssetBalance.objects.select_for_update().get(wallet=hold.wallet, asset_network=hold.asset_network)
        balance.held_atomic -= hold.amount_atomic
        if target == "CAPTURED":
            balance.posted_atomic -= hold.amount_atomic
            balance.save(update_fields=["held_atomic", "posted_atomic", "updated_at"])
        else:
            balance.save(update_fields=["held_atomic", "updated_at"])
        hold.state = target
        hold.save(update_fields=["state", "updated_at"])
        return hold


def capture_hold(hold_id):
    return _transition_hold(hold_id, "CAPTURED")


def release_hold(hold_id):
    return _transition_hold(hold_id, "RELEASED")
