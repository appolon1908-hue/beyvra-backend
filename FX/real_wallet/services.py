import hashlib
import json
from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    AssetBalance,
    AuditEvent,
    BalanceHold,
    Deposit,
    FeatureFlag,
    IdempotencyRecord,
    InternalTransfer,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    OutboxEvent,
    WebhookDelivery,
    WebhookEvent,
    Withdrawal,
    WithdrawalAddress,
    WithdrawalApproval,
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


def record_audit(*, tenant, actor, action, resource_type, resource_id, outcome, reason="", request_id="", correlation_id=None, metadata=None):
    """Record an audit event with caller-supplied safe metadata only."""
    return AuditEvent.objects.create(
        tenant=tenant, actor=actor, action=action, resource_type=resource_type,
        resource_id=resource_id, outcome=outcome, reason=reason[:2000],
        request_id=request_id[:128], correlation_id=correlation_id, metadata=metadata or {},
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
    record_audit(
        tenant=tenant, actor=actor, action="withdrawal.requested", resource_type="withdrawal",
        resource_id=withdrawal.id, outcome="accepted",
    )
    return withdrawal


@transaction.atomic
def create_internal_transfer(*, tenant, actor, source_wallet, destination_wallet, asset_network,
                             amount_atomic, idempotency_key, request_payload):
    if not is_feature_enabled("real_wallet_internal_transfers_enabled"):
        raise RealWalletFeatureDisabled("real_wallet_internal_transfers_enabled")
    if source_wallet.id == destination_wallet.id or source_wallet.tenant_id != tenant.id or destination_wallet.tenant_id != tenant.id:
        raise ValueError("invalid transfer wallets")
    amount = Decimal(str(amount_atomic))
    if amount <= 0:
        raise ValueError("transfer amount must be positive")
    record, created = reserve_idempotency(
        tenant=tenant, actor=actor, endpoint="/api/v1/transfers", method="POST",
        key=idempotency_key, request_payload=request_payload,
    )
    if not created and record.resource_id:
        return InternalTransfer.objects.get(pk=record.resource_id)
    first, second = sorted((source_wallet.id, destination_wallet.id), key=str)
    balances = {
        balance.wallet_id: balance
        for balance in AssetBalance.objects.select_for_update().filter(
            wallet_id__in=(first, second), asset_network=asset_network
        )
    }
    source_balance = balances.get(source_wallet.id)
    destination_balance = balances.get(destination_wallet.id)
    if source_balance is None or destination_balance is None or source_balance.available_atomic < amount:
        raise ValueError("insufficient available balance")
    source_account, _ = LedgerAccount.objects.get_or_create(
        tenant=tenant, owner_type="WALLET", owner_id=source_wallet.id, asset=asset_network.asset,
        account_code="CUSTOMER_AVAILABLE", defaults={"account_type": "LIABILITY", "normal_side": "CREDIT"},
    )
    destination_account, _ = LedgerAccount.objects.get_or_create(
        tenant=tenant, owner_type="WALLET", owner_id=destination_wallet.id, asset=asset_network.asset,
        account_code="CUSTOMER_AVAILABLE", defaults={"account_type": "LIABILITY", "normal_side": "CREDIT"},
    )
    transfer = InternalTransfer.objects.create(
        tenant=tenant, source_wallet=source_wallet, destination_wallet=destination_wallet,
        asset_network=asset_network, amount_atomic=amount, state="COMPLETED", idempotency_key=idempotency_key,
    )
    post_transaction(
        tenant=tenant, transaction_type="INTERNAL_TRANSFER", idempotency_key=f"transfer-ledger:{idempotency_key}",
        entries=[
            {"account": source_account, "asset": asset_network.asset, "direction": "DEBIT", "amount_atomic": amount},
            {"account": destination_account, "asset": asset_network.asset, "direction": "CREDIT", "amount_atomic": amount},
        ], metadata={"transfer_id": str(transfer.id)},
    )
    source_balance.posted_atomic -= amount
    destination_balance.posted_atomic += amount
    source_balance.save(update_fields=["posted_atomic", "updated_at"])
    destination_balance.save(update_fields=["posted_atomic", "updated_at"])
    enqueue_outbox(
        tenant=tenant, aggregate_type="transfer", aggregate_id=transfer.id,
        event_type="wallet.transfer.completed", payload={"transfer_id": str(transfer.id)},
    )
    complete_idempotency(
        record, resource_type="internal_transfer", resource_id=transfer.id,
        response_status=201, response_body={"transfer_id": str(transfer.id)},
    )
    record_audit(
        tenant=tenant, actor=actor, action="transfer.completed", resource_type="internal_transfer",
        resource_id=transfer.id, outcome="completed",
    )
    return transfer


@transaction.atomic
def record_detected_deposit(*, tenant, wallet, asset_network, transaction_hash, output_index,
                            amount_atomic, confirmations=0):
    if not is_feature_enabled("real_wallet_deposits_enabled"):
        raise RealWalletFeatureDisabled("real_wallet_deposits_enabled")
    amount = Decimal(str(amount_atomic))
    if amount <= 0:
        raise ValueError("deposit amount must be positive")
    deposit, created = Deposit.objects.get_or_create(
        asset_network=asset_network, transaction_hash=transaction_hash, output_index=output_index,
        defaults={
            "tenant": tenant, "wallet": wallet, "amount_atomic": amount,
            "confirmations": confirmations, "state": "CONFIRMING" if confirmations else "DETECTED",
        },
    )
    if created:
        enqueue_outbox(
            tenant=tenant, aggregate_type="deposit", aggregate_id=deposit.id,
            event_type="wallet.deposit.detected", payload={"deposit_id": str(deposit.id)},
        )
        record_audit(
            tenant=tenant, actor=None, action="deposit.detected", resource_type="deposit",
            resource_id=deposit.id, outcome="accepted",
        )
    return deposit


@transaction.atomic
def credit_deposit(*, deposit_id, required_confirmations):
    if not is_feature_enabled("real_wallet_deposits_enabled"):
        raise RealWalletFeatureDisabled("real_wallet_deposits_enabled")
    deposit = Deposit.objects.select_for_update().select_related("wallet", "asset_network__asset").get(pk=deposit_id)
    if deposit.state == "CREDITED":
        return deposit
    if deposit.state in {"REJECTED", "REVERSED", "REORGED"}:
        raise ValueError("deposit cannot be credited")
    if deposit.confirmations < required_confirmations:
        raise ValueError("deposit confirmations are insufficient")
    balance, _ = AssetBalance.objects.select_for_update().get_or_create(
        wallet=deposit.wallet, asset_network=deposit.asset_network,
        defaults={"posted_atomic": 0},
    )
    platform_account, _ = LedgerAccount.objects.get_or_create(
        tenant=deposit.tenant, owner_type="PLATFORM", owner_id=None, asset=deposit.asset_network.asset,
        account_code="PLATFORM_HOT_WALLET", defaults={"account_type": "ASSET", "normal_side": "DEBIT"},
    )
    customer_account, _ = LedgerAccount.objects.get_or_create(
        tenant=deposit.tenant, owner_type="WALLET", owner_id=deposit.wallet_id, asset=deposit.asset_network.asset,
        account_code="CUSTOMER_AVAILABLE", defaults={"account_type": "LIABILITY", "normal_side": "CREDIT"},
    )
    ledger_tx = post_transaction(
        tenant=deposit.tenant, transaction_type="DEPOSIT_CREDIT",
        idempotency_key=f"deposit-credit:{deposit.id}",
        entries=[
            {"account": platform_account, "asset": deposit.asset_network.asset, "direction": "DEBIT", "amount_atomic": deposit.amount_atomic},
            {"account": customer_account, "asset": deposit.asset_network.asset, "direction": "CREDIT", "amount_atomic": deposit.amount_atomic},
        ], metadata={"deposit_id": str(deposit.id)},
    )
    balance.posted_atomic += deposit.amount_atomic
    balance.save(update_fields=["posted_atomic", "updated_at"])
    deposit.state = "CREDITED"
    deposit.ledger_transaction = ledger_tx
    deposit.save(update_fields=["state", "ledger_transaction", "updated_at"])
    enqueue_outbox(
        tenant=deposit.tenant, aggregate_type="deposit", aggregate_id=deposit.id,
        event_type="wallet.deposit.credited", payload={"deposit_id": str(deposit.id)},
    )
    record_audit(
        tenant=deposit.tenant, actor=None, action="deposit.credited", resource_type="deposit",
        resource_id=deposit.id, outcome="completed",
    )
    return deposit


@transaction.atomic
def cancel_withdrawal(*, withdrawal_id, actor):
    withdrawal = Withdrawal.objects.select_for_update().select_related("hold", "wallet").get(pk=withdrawal_id)
    if withdrawal.wallet.owner_id != actor.id:
        raise ValueError("withdrawal is not owned by actor")
    if withdrawal.state not in {"REQUESTED", "USER_CONFIRMATION_REQUIRED", "COMPLIANCE_REVIEW", "RISK_REVIEW", "MANUAL_REVIEW"}:
        raise ValueError("withdrawal is not cancellable")
    if withdrawal.hold_id:
        release_hold(withdrawal.hold_id)
    withdrawal.state = "CANCELLED"
    withdrawal.save(update_fields=["state", "updated_at"])
    enqueue_outbox(
        tenant=withdrawal.tenant, aggregate_type="withdrawal", aggregate_id=withdrawal.id,
        event_type="wallet.withdrawal.cancelled", payload={"withdrawal_id": str(withdrawal.id)},
    )
    record_audit(
        tenant=withdrawal.tenant, actor=actor, action="withdrawal.cancelled", resource_type="withdrawal",
        resource_id=withdrawal.id, outcome="accepted",
    )
    return withdrawal


@transaction.atomic
def fail_withdrawal(*, withdrawal_id, reason):
    withdrawal = Withdrawal.objects.select_for_update().select_related("hold", "asset_network__asset").get(pk=withdrawal_id)
    if withdrawal.state in {"COMPLETED", "CANCELLED"}:
        raise ValueError("withdrawal cannot be failed")
    if withdrawal.state == "FAILED":
        return withdrawal
    if withdrawal.hold_id and withdrawal.hold.state == "ACTIVE":
        release_hold(withdrawal.hold_id)
    withdrawal.state = "FAILED"
    withdrawal.save(update_fields=["state", "updated_at"])
    enqueue_outbox(
        tenant=withdrawal.tenant, aggregate_type="withdrawal", aggregate_id=withdrawal.id,
        event_type="wallet.withdrawal.failed", payload={"withdrawal_id": str(withdrawal.id), "reason": reason},
    )
    record_audit(
        tenant=withdrawal.tenant, actor=None, action="withdrawal.failed", resource_type="withdrawal",
        resource_id=withdrawal.id, outcome="failed", reason=reason,
    )
    return withdrawal


@transaction.atomic
def complete_withdrawal(*, withdrawal_id, blockchain_transaction):
    withdrawal = Withdrawal.objects.select_for_update().select_related("hold", "wallet", "asset_network__asset").get(pk=withdrawal_id)
    if withdrawal.state == "COMPLETED":
        return withdrawal
    if withdrawal.state not in {"SIGNED", "BROADCAST", "CONFIRMING"}:
        raise ValueError("withdrawal is not ready for completion")
    platform_account, _ = LedgerAccount.objects.get_or_create(
        tenant=withdrawal.tenant, owner_type="PLATFORM", owner_id=None, asset=withdrawal.asset_network.asset,
        account_code="PLATFORM_HOT_WALLET", defaults={"account_type": "ASSET", "normal_side": "DEBIT"},
    )
    customer_account, _ = LedgerAccount.objects.get_or_create(
        tenant=withdrawal.tenant, owner_type="WALLET", owner_id=withdrawal.wallet_id, asset=withdrawal.asset_network.asset,
        account_code="CUSTOMER_AVAILABLE", defaults={"account_type": "LIABILITY", "normal_side": "CREDIT"},
    )
    post_transaction(
        tenant=withdrawal.tenant, transaction_type="WITHDRAWAL_CAPTURE",
        idempotency_key=f"withdrawal-capture:{withdrawal.id}",
        entries=[
            {"account": customer_account, "asset": withdrawal.asset_network.asset, "direction": "DEBIT", "amount_atomic": withdrawal.amount_atomic},
            {"account": platform_account, "asset": withdrawal.asset_network.asset, "direction": "CREDIT", "amount_atomic": withdrawal.amount_atomic},
        ], metadata={"withdrawal_id": str(withdrawal.id), "blockchain_transaction": blockchain_transaction},
    )
    if withdrawal.hold_id and withdrawal.hold.state == "ACTIVE":
        capture_hold(withdrawal.hold_id)
    withdrawal.state = "COMPLETED"
    withdrawal.blockchain_transaction = blockchain_transaction
    withdrawal.save(update_fields=["state", "blockchain_transaction", "updated_at"])
    enqueue_outbox(
        tenant=withdrawal.tenant, aggregate_type="withdrawal", aggregate_id=withdrawal.id,
        event_type="wallet.withdrawal.completed", payload={"withdrawal_id": str(withdrawal.id)},
    )
    record_audit(
        tenant=withdrawal.tenant, actor=None, action="withdrawal.completed", resource_type="withdrawal",
        resource_id=withdrawal.id, outcome="completed",
    )
    return withdrawal


@transaction.atomic
def approve_withdrawal(*, withdrawal_id, approver, decision, reason=""):
    withdrawal = Withdrawal.objects.select_for_update().select_related("wallet", "tenant").get(pk=withdrawal_id)
    if not withdrawal.tenant.memberships.filter(user=approver).exists():
        raise ValueError("approver is not a tenant member")
    if withdrawal.wallet.owner_id == approver.id:
        raise ValueError("initiator cannot approve own withdrawal")
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("invalid approval decision")
    approval, created = WithdrawalApproval.objects.get_or_create(
        withdrawal=withdrawal, approver=approver,
        defaults={"decision": decision, "reason": reason[:2000]},
    )
    if not created:
        return withdrawal
    if decision == "REJECTED":
        withdrawal.state = "REJECTED"
    elif withdrawal.approvals.filter(decision="APPROVED").count() >= 2:
        withdrawal.state = "APPROVED"
    withdrawal.save(update_fields=["state", "updated_at"])
    record_audit(
        tenant=withdrawal.tenant, actor=approver, action="withdrawal.approval_recorded",
        resource_type="withdrawal", resource_id=withdrawal.id, outcome=decision.lower(),
    )
    return withdrawal
