import uuid
from django.conf import settings
from django.db import models


class EffectivePolicy(models.Model):
    code=models.CharField(max_length=64); policy_version=models.PositiveIntegerField(); status=models.CharField(max_length=16,default="DRAFT")
    effective_from=models.DateTimeField(); effective_to=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta: abstract=True


class MarginPolicy(EffectivePolicy):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); name=models.CharField(max_length=128)
    asset_class=models.CharField(max_length=24); instrument_id=models.UUIDField(null=True,blank=True); account_plan=models.CharField(max_length=64,blank=True); jurisdiction=models.CharField(max_length=8,blank=True)
    initial_margin_rate=models.DecimalField(max_digits=20,decimal_places=10); maintenance_margin_rate=models.DecimalField(max_digits=20,decimal_places=10)
    short_margin_rate=models.DecimalField(max_digits=20,decimal_places=10,null=True,blank=True); intraday_margin_rate=models.DecimalField(max_digits=20,decimal_places=10,null=True,blank=True); overnight_margin_rate=models.DecimalField(max_digits=20,decimal_places=10,null=True,blank=True)


class CollateralPolicy(EffectivePolicy):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); asset=models.CharField(max_length=32); network=models.CharField(max_length=64,blank=True)
    eligible=models.BooleanField(default=False); haircut_rate=models.DecimalField(max_digits=20,decimal_places=10); valuation_currency=models.CharField(max_length=12); max_concentration_rate=models.DecimalField(max_digits=20,decimal_places=10,null=True,blank=True)


class ExposureLimit(EffectivePolicy):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); scope_type=models.CharField(max_length=24); scope_ref=models.CharField(max_length=128)
    limit_type=models.CharField(max_length=40); limit_value=models.DecimalField(max_digits=30,decimal_places=10); currency=models.CharField(max_length=12,blank=True); asset_class=models.CharField(max_length=24,blank=True); instrument_id=models.UUIDField(null=True,blank=True); venue_id=models.CharField(max_length=64,blank=True); side=models.CharField(max_length=8,blank=True)


class MarginCall(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); account=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="margin_calls")
    state=models.CharField(max_length=24,default="OPEN"); triggered_at=models.DateTimeField(); required_amount=models.DecimalField(max_digits=30,decimal_places=10); currency=models.CharField(max_length=12); deadline=models.DateTimeField(null=True,blank=True); reason_codes=models.JSONField(default=list); policy_version=models.PositiveIntegerField(); resolved_at=models.DateTimeField(null=True,blank=True); resolution_code=models.CharField(max_length=64,blank=True); simulation=models.BooleanField(default=True)
    class Meta: constraints=[models.UniqueConstraint(fields=("account",),condition=models.Q(state__in=("OPEN","NOTIFIED","ACKNOWLEDGED","ESCALATED","LIQUIDATION_ELIGIBLE")),name="risk_one_active_margin_call")]


class LiquidationPolicy(EffectivePolicy):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); priority_method=models.CharField(max_length=40); target_margin_ratio=models.DecimalField(max_digits=20,decimal_places=10); minimum_buffer=models.DecimalField(max_digits=30,decimal_places=10); max_orders_per_cycle=models.PositiveIntegerField(); max_notional_per_cycle=models.DecimalField(max_digits=30,decimal_places=10)


class LiquidationPlan(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); account=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="liquidation_plans")
    state=models.CharField(max_length=32,default="PROPOSED"); trigger_reason=models.CharField(max_length=96); required_reduction=models.DecimalField(max_digits=30,decimal_places=10); currency=models.CharField(max_length=12); target_margin_ratio=models.DecimalField(max_digits=20,decimal_places=10); policy_version=models.PositiveIntegerField(); created_at=models.DateTimeField(auto_now_add=True); approved_at=models.DateTimeField(null=True,blank=True); completed_at=models.DateTimeField(null=True,blank=True); simulation=models.BooleanField(default=True)


class LiquidationPlanItem(models.Model):
    plan=models.ForeignKey(LiquidationPlan,on_delete=models.PROTECT,related_name="items"); instrument_id=models.UUIDField(); side=models.CharField(max_length=8); quantity=models.DecimalField(max_digits=30,decimal_places=10); estimated_price=models.DecimalField(max_digits=30,decimal_places=10); estimated_notional=models.DecimalField(max_digits=30,decimal_places=10); priority=models.PositiveIntegerField(); reason=models.CharField(max_length=96); state=models.CharField(max_length=32,default="PROPOSED"); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)


class RiskAudit(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); event_type=models.CharField(max_length=64); account_ref=models.CharField(max_length=128); entity_ref=models.CharField(max_length=128); occurred_at=models.DateTimeField(); evidence_hash=models.CharField(max_length=64); metadata_safe=models.JSONField(default=dict)
