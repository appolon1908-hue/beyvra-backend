import hashlib
import json
from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    AssetBalance,
    BalanceHold,
    FeatureFlag,
    IdempotencyRecord,
    LedgerEntry,
    LedgerTransaction,
    OutboxEvent,
    WebhookDelivery,
    WebhookEvent,
    Withdrawal,
    WithdrawalAddress,
)

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


class IdempotencyConflict(Exception):
    code = "IDEMPOTENCY_CONFLICT"


def is_feature_enabled(key: str) -> bool:
    return FeatureFlag.objects.filter(key=key, enabled=True).exists()


def canonical_request_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


@transaction.atomic
def reserve_idempotency(*, tenant, actor, endpoint, method, key, request_payload, ttl_seconds=86400):
    """Reserve a value-changing request in PostgreSQL before side effects."""
    request_hash = canonical_request_hash(request_payload)
    record = IdempotencyRecord.objects.select_for_update().filter(
        tenant=tenant, actor=actor, endpoint=endpoint, method=method, key=key
    ).first()
    if record:
        if record.request_hash != request_hash:
            raise IdempotencyConflict("idempotency key was reused with a different request")
        return record, False
    return IdempotencyRecord.objects.create(
        tenant=tenant, actor=actor, endpoint=endpoint, method=method, key=key,
        request_hash=request_hash, expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
    ), True


def complete_idempotency(record, *, resource_type, resource_id, response_status, response_body):
    record.resource_type = resource_type
    record.resource_id = resource_id
    record.response_status = response_status
    record.response_body = response_body
    record.save(update_fields=["resource_type", "resource_id", "response_status", "response_body", "updated_at"])
    return record


def enqueue_outbox(*, tenant, aggregate_type, aggregate_id, event_type, payload, occurred_at=None,
                   correlation_id=None, causation_id=None):
    """Persist an event in the caller's transaction; no broker call is made here."""
    return OutboxEvent.objects.create(
        tenant=tenant,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        occurred_at=occurred_at or timezone.now(),
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


@transaction.atomic
def create_webhook_delivery(*, tenant, subscription, event_id, event_type, payload, occurred_at=None):
    event, _ = WebhookEvent.objects.get_or_create(
        tenant=tenant,
        event_id=event_id,
        defaults={"event_type": event_type, "payload": payload, "occurred_at": occurred_at or timezone.now()},
    )
    delivery, created = WebhookDelivery.objects.get_or_create(subscription=subscription, event=event)
    return delivery, created


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


@transaction.atomic
def request_withdrawal(*, tenant, actor, wallet, withdrawal_address, amount_atomic, idempotency_key, request_payload):
    """Create a withdrawal request and hold funds without calling custody."""
    if not is_feature_enabled("real_wallet_withdrawals_enabled"):
        raise RealWalletFeatureDisabled("real_wallet_withdrawals_enabled")
    amount = Decimal(str(amount_atomic))
    if amount <= 0:
        raise ValueError("withdrawal amount must be positive")
    record, created = reserve_idempotency(
        tenant=tenant, actor=actor, endpoint="/api/v1/withdrawals", method="POST",
        key=idempotency_key, request_payload=request_payload,
    )
    if not created and record.resource_id:
        return Withdrawal.objects.get(pk=record.resource_id)
    address = WithdrawalAddress.objects.select_for_update().filter(
        id=withdrawal_address, tenant=tenant, wallet=wallet, status="ACTIVE", risk_state="CLEARED"
    ).first()
    if address is None:
        raise ValueError("withdrawal address is not active")
    if address.cooling_until and address.cooling_until > timezone.now():
        raise ValueError("withdrawal address is in a cooling period")
    hold = create_hold(
        tenant=tenant, wallet=wallet, asset_network=address.asset_network, amount_atomic=amount,
        reason="WITHDRAWAL", idempotency_key=f"withdrawal:{idempotency_key}",
    )
    withdrawal = Withdrawal.objects.create(
        tenant=tenant, wallet=wallet, asset_network=address.asset_network, destination=address.address,
        amount_atomic=amount, state="REQUESTED", hold=hold, idempotency_key=idempotency_key,
    )
    enqueue_outbox(
        tenant=tenant, aggregate_type="withdrawal", aggregate_id=withdrawal.id,
        event_type="wallet.withdrawal.requested", payload={"withdrawal_id": str(withdrawal.id)},
    )
    complete_idempotency(
        record, resource_type="withdrawal", resource_id=withdrawal.id,
        response_status=202, response_body={"withdrawal_id": str(withdrawal.id)},
    )
    return withdrawal
