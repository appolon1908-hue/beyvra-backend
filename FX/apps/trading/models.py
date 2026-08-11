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
    state = models.CharField(
        max_length=24,
        choices=[(value.value, value.value) for value in OrderState],
        default=OrderState.PENDING.value,
    )
    simulation = models.BooleanField(default=True, editable=False)
    eligibility_policy_version = models.CharField(max_length=32, default="")
    eligibility_result = models.CharField(max_length=20, default="DENIED")
    eligibility_reason_codes = models.JSONField(default=list)
    eligibility_evaluated_at = models.DateTimeField(null=True)
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("tenant_ref", "subject_ref", "idempotency_key"), condition=~models.Q(idempotency_key=""), name="unique_sim_order_idempotency")]


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
