import uuid

from django.db import models

from apps.trading.domain.orders import OrderSide, OrderState, OrderType


class TradingOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    subject_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    instrument_id = models.CharField(max_length=64)
    order_type = models.CharField(max_length=16, choices=[(value.value, value.value) for value in OrderType])
    side = models.CharField(max_length=8, choices=[(value.value, value.value) for value in OrderSide])
    quantity = models.DecimalField(max_digits=36, decimal_places=18)
    limit_price = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    stop_price = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    filled_quantity = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    average_fill_price = models.DecimalField(max_digits=36, decimal_places=18, null=True)
    risk_decision_id = models.UUIDField(null=True)
    reservation_id = models.UUIDField(null=True)
    simulation = models.BooleanField(default=False)
    state = models.CharField(
        max_length=24,
        choices=[(value.value, value.value) for value in OrderState],
        default=OrderState.PENDING.value,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class RiskDecision(models.Model):
    class Decision(models.TextChoices):
        ALLOW = "ALLOW"
        DENY = "DENY"
        REVIEW = "REVIEW"

    decision_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    subject_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    order_id = models.UUIDField(null=True)
    decision = models.CharField(max_length=8, choices=Decision.choices)
    reason_codes = models.JSONField(default=list)
    policy_version = models.CharField(max_length=32)
    inputs_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)


class SimulatedAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_ref = models.CharField(max_length=128)
    subject_ref = models.CharField(max_length=128)
    account_ref = models.CharField(max_length=128)
    status = models.CharField(max_length=16, default="ACTIVE")
    quote_currency = models.CharField(max_length=16, default="USD")
    total_balance = models.DecimalField(max_digits=36, decimal_places=18, default=10000)
    pending_balance = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("tenant_ref", "subject_ref", "account_ref"), name="simulation_account_scope_unique")]


class SimulatedReservation(models.Model):
    class State(models.TextChoices):
        ACTIVE = "ACTIVE"
        RELEASED = "RELEASED"
        CONSUMED = "CONSUMED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(SimulatedAccount, on_delete=models.PROTECT, related_name="reservations")
    order_id = models.UUIDField(unique=True)
    asset = models.CharField(max_length=32)
    original_amount = models.DecimalField(max_digits=36, decimal_places=18)
    remaining_amount = models.DecimalField(max_digits=36, decimal_places=18)
    state = models.CharField(max_length=16, choices=State.choices, default=State.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SimulatedTrade(models.Model):
    trade_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(TradingOrder, on_delete=models.PROTECT, related_name="simulated_trades")
    execution_id = models.CharField(max_length=128, unique=True)
    instrument_id = models.CharField(max_length=64)
    side = models.CharField(max_length=8)
    quantity = models.DecimalField(max_digits=36, decimal_places=18)
    price = models.DecimalField(max_digits=36, decimal_places=18)
    fee = models.DecimalField(max_digits=36, decimal_places=18)
    executed_at = models.DateTimeField()
    simulation = models.BooleanField(default=True)


class SimulatedPosition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(SimulatedAccount, on_delete=models.PROTECT, related_name="positions")
    instrument_id = models.CharField(max_length=64)
    quantity = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    average_price = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    realized_pnl = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("account", "instrument_id"), name="simulation_position_unique")]
