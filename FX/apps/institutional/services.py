from collections import defaultdict
from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    AllocationGroup, InstitutionalAccount, InstitutionalAuditEvent,
    InstitutionalOutboxEvent, InstitutionalPosition, InstitutionalReconciliationRun,
    InstitutionalSubaccount, InstitutionalTradeAllocationInstruction,
    InstitutionalTradeAllocationLine, OmnibusAccount, SegregatedCustodyAccount,
)


LIVE_CAPABILITIES = {"LIVE_EXECUTION", "MARGIN", "SHORTING", "OMNIBUS", "SEGREGATED", "DVP", "FOP"}
POLICY_VERSION = "institutional-v1"


def _evidence(institution, event_type, obj, actor=None, metadata=None):
    InstitutionalAuditEvent.objects.create(
        institution=institution, actor=actor, event_type=event_type,
        object_type=obj.__class__.__name__, object_ref=str(obj.pk), metadata=metadata or {},
    )
    InstitutionalOutboxEvent.objects.create(
        institution=institution, event_type=event_type, aggregate_ref=str(obj.pk),
        payload={"schema_version": 1, "institution_id": str(institution.pk), "object_ref": str(obj.pk)},
    )


class InstitutionalAccountService:
    @staticmethod
    def get(*, tenant, institution_id):
        return InstitutionalAccount.objects.get(pk=institution_id, tenant=tenant)

    @staticmethod
    def list(*, tenant):
        return InstitutionalAccount.objects.filter(tenant=tenant).order_by("institution_code", "id")

    @staticmethod
    @transaction.atomic
    def create_internal(*, tenant, actor, **data):
        account = InstitutionalAccount(tenant=tenant, **data)
        account.full_clean()
        account.save()
        _evidence(account, "institutional.account.created.v1", account, actor)
        return account

    @staticmethod
    @transaction.atomic
    def update_status(*, account, status, actor):
        before = account.status
        account.status = status
        account.full_clean()
        account.save(update_fields=("status", "updated_at"))
        _evidence(account, "institutional.account.status.updated.v1", account, actor, {"before": before, "after": status})
        return account

    @staticmethod
    def get_hierarchy(*, account):
        rows = account.subaccounts.select_related("parent_subaccount").order_by("code", "id")
        return [{"id": str(row.id), "code": row.code, "display_name": row.display_name, "status": row.status, "parent_subaccount_id": str(row.parent_subaccount_id) if row.parent_subaccount_id else None} for row in rows]


class SubaccountService:
    @staticmethod
    @transaction.atomic
    def create(*, institution, actor, **data):
        row = InstitutionalSubaccount(institution=institution, tenant=institution.tenant, **data)
        row.full_clean()
        row.save()
        _evidence(institution, "institutional.subaccount.updated.v1", row, actor)
        return row


class AllocationService:
    QUANTUM = Decimal("0.000000000000000001")

    @classmethod
    @transaction.atomic
    def allocate_fixed_percent(cls, *, institution, trade_id, source_account, group, quantity, price, idempotency_key, actor=None):
        existing = InstitutionalTradeAllocationInstruction.objects.filter(institution=institution, trade_id=trade_id).first()
        if existing:
            return existing
        members = list(group.members.filter(status="ACTIVE").select_related("subaccount").order_by("priority", "id"))
        if not members or any(member.weight is None for member in members):
            raise ValueError("ALLOCATION_INVALID")
        if sum((member.weight for member in members), Decimal("0")) != Decimal("1"):
            raise ValueError("ALLOCATION_WEIGHTS_MUST_EQUAL_ONE")
        instruction = InstitutionalTradeAllocationInstruction.objects.create(
            institution=institution, trade_id=trade_id, allocation_group=group,
            source_account=source_account, allocation_method="FIXED_PERCENT", state="CALCULATED",
            policy_version=POLICY_VERSION, canonical_quantity=quantity, idempotency_key=idempotency_key,
        )
        allocated = Decimal("0")
        for index, member in enumerate(members):
            line_quantity = quantity - allocated if index == len(members) - 1 else (quantity * member.weight).quantize(cls.QUANTUM, rounding=ROUND_DOWN)
            allocated += line_quantity
            InstitutionalTradeAllocationLine.objects.create(
                instruction=instruction, target_subaccount=member.subaccount,
                quantity=line_quantity, notional=(line_quantity * price).quantize(cls.QUANTUM), status="VALIDATED",
            )
        instruction.state = "ALLOCATED"
        instruction.save(update_fields=("state", "updated_at"))
        _evidence(institution, "institutional.allocation.created.v1", instruction, actor)
        return instruction


class InstitutionAggregationService:
    @staticmethod
    def positions(*, institution):
        rows = institution.positions.values("instrument_id").annotate(quantity=Sum("quantity")).order_by("instrument_id")
        return [{"instrument_id": row["instrument_id"], "quantity": str(row["quantity"] or Decimal("0"))} for row in rows]

    @staticmethod
    def exposure(*, institution):
        positions = InstitutionAggregationService.positions(institution=institution)
        gross = sum((abs(Decimal(row["quantity"])) for row in positions), Decimal("0"))
        net = sum((Decimal(row["quantity"]) for row in positions), Decimal("0"))
        return {"gross_quantity_exposure": str(gross), "net_quantity_exposure": str(net), "policy_version": POLICY_VERSION, "simulation": True}

    @staticmethod
    def cash_view(*, institution):
        rows = defaultdict(Decimal)
        for item in institution.omnibus_accounts.values("cash_attributions__currency").annotate(amount=Sum("cash_attributions__amount")):
            if item["cash_attributions__currency"]:
                rows[item["cash_attributions__currency"]] += item["amount"] or Decimal("0")
        return [{"currency": key, "amount": str(value), "simulation": True} for key, value in sorted(rows.items())]


class InstitutionalRiskService:
    @staticmethod
    def evaluate(*, institution, subaccount=None):
        institution_exposure = InstitutionAggregationService.exposure(institution=institution)
        if institution.status != "ACTIVE" or (subaccount and subaccount.status != "ACTIVE"):
            result, reasons = "DENIED", ["INSTITUTION_RESTRICTED" if institution.status != "ACTIVE" else "SUBACCOUNT_RESTRICTED"]
        else:
            result, reasons = "ALLOWED", []
        return {"result": result, "reason_codes": reasons, "institution_exposure": institution_exposure, "policy_version": POLICY_VERSION, "simulation": True}


class InstitutionalAccountReconciler:
    @staticmethod
    @transaction.atomic
    def run(*, institution, actor=None):
        violations = []
        for row in institution.subaccounts.select_related("tenant"):
            if row.tenant_id != institution.tenant_id:
                violations.append({"code": "SUBACCOUNT_WRONG_TENANT", "object_ref": str(row.pk)})
        for position in institution.positions.select_related("subaccount"):
            if position.tenant_id != institution.tenant_id or position.subaccount.institution_id != institution.id:
                violations.append({"code": "POSITION_WITHOUT_SUBACCOUNT", "object_ref": str(position.pk)})
        for omnibus in institution.omnibus_accounts.all():
            for position in omnibus.beneficial_positions.select_related("subaccount"):
                if position.subaccount.institution_id != institution.id:
                    violations.append({"code": "OMNIBUS_ATTRIBUTION_MISMATCH", "object_ref": str(position.pk)})
        for account in institution.segregated_accounts.select_related("subaccount"):
            if account.subaccount.institution_id != institution.id:
                violations.append({"code": "SEGREGATED_ACCOUNT_MAPPING_CONFLICT", "object_ref": str(account.pk)})
        for instruction in institution.trade_allocations.prefetch_related("lines"):
            total = sum((line.quantity for line in instruction.lines.all()), Decimal("0"))
            if total != instruction.canonical_quantity:
                violations.append({"code": "ALLOCATION_MISMATCH", "object_ref": str(instruction.pk)})
        run = InstitutionalReconciliationRun.objects.create(
            institution=institution, status="PASS" if not violations else "VIOLATIONS", violations=violations, completed_at=timezone.now(),
        )
        _evidence(institution, "institutional.reconciliation.completed.v1", run, actor, {"violation_count": len(violations)})
        return run


def deny_live_institutional_operation():
    return {"allowed": False, "code": "FEATURE_DISABLED", "outbound_live_requests": 0, "real_financial_effects": 0}
