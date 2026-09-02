import uuid
from decimal import Decimal

from django.db import transaction
from django.forms.models import model_to_dict
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import IdempotencyConflict, begin_idempotent_request, complete_idempotent_request

from integrations.models import OrganizationMembership

from .models import (
    FundingRequirement, IntradayFundingWindow, LiquidityForecast, LiquiditySnapshot,
    LiquidityStressScenario, TreasuryException, TreasuryReconciliationRun,
    TreasuryTransferPlan,
)
from .services import (
    CashPositionService, CollateralMobilityService, LiquidityForecastService,
    LiquidityService, LiquidityStressService, SettlementFundingService,
    TreasuryAccountService, TreasuryCollateralService, TreasuryPlanner,
    TreasuryReconciler,
)


COMMAND_PARAMETERS = [
    OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Request-ID", str, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Correlation-ID", str, OpenApiParameter.HEADER, required=False),
]
VERSIONED_COMMAND_PARAMETERS = [*COMMAND_PARAMETERS, OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)]


def command_context(request, *, require_version=False):
    key = request.headers.get("Idempotency-Key", "").strip()
    request_id = request.headers.get("X-Request-ID", "").strip()
    expected_version = request.headers.get("If-Match", "").strip()
    if not key or len(key) > 255 or not request_id or len(request_id) > 128:
        return None, Response({"code": "VALIDATION_ERROR", "message": "Idempotency-Key and X-Request-ID are required."}, status=400)
    if require_version and not expected_version:
        return None, Response({"code": "PRECONDITION_REQUIRED", "message": "If-Match is required."}, status=428)
    try:
        correlation_id = uuid.UUID(request.headers.get("X-Correlation-ID") or request_id)
    except (TypeError, ValueError):
        return None, Response({"code": "VALIDATION_ERROR", "message": "The correlation identifier must be a UUID."}, status=400)
    return (key, request_id, correlation_id, expected_version), None


def begin_command(request, *, tenant, key, payload):
    return begin_idempotent_request(
        key=key, tenant_ref=tenant.pk, actor_ref=request.user.pk, endpoint=request.path,
        method=request.method, request_data={"api_version": "v1", **payload},
    )


def replay(record):
    if record.response_status is None or record.response_body is None:
        return Response({"code": "COMMAND_IN_PROGRESS"}, status=409)
    return Response(record.response_body, status=record.response_status)


def command_audit(request, *, tenant, action, resource_type, resource_id, request_id, correlation_id, context=None):
    ApplicationAuditEvent.objects.create(
        actor_ref=str(request.user.pk), action=action, resource_type=resource_type, resource_id=str(resource_id),
        request_id=request_id, correlation_id=correlation_id, context={"tenant_ref": str(tenant.pk), "simulation": True, **(context or {})},
        reason="TREASURY_OPERATOR_COMMAND", occurred_at=timezone.now(),
    )


def exception_version(item):
    return f"{item.state}:{item.severity}:{item.assigned_to_id or '-'}"


def serialize(value):
    if hasattr(value, "_meta"):
        data = model_to_dict(value)
        data["id"] = value.pk
        return serialize(data)
    if isinstance(value, dict): return {k: serialize(v) for k, v in value.items() if k not in {"external_account_ref", "provider_id"}}
    if isinstance(value, (list, tuple)): return [serialize(v) for v in value]
    if isinstance(value, Decimal): return format(value, "f")
    if isinstance(value, uuid.UUID): return str(value)
    if hasattr(value, "isoformat"): return value.isoformat()
    return value


class TreasuryAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    operator_roles = None

    def membership(self, request):
        qs = OrganizationMembership.objects.select_related("organization").filter(user=request.user, organization__is_active=True)
        tenant_header = request.headers.get("X-Tenant-ID")
        if tenant_header: qs = qs.filter(organization_id=tenant_header)
        membership = qs.first()
        if not membership: return None
        if self.operator_roles and not (request.user.is_superuser or membership.role in self.operator_roles): return None
        return membership

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.member = self.membership(request)
        if not self.member:
            self.permission_denied(request, message="TREASURY_DATA_UNAVAILABLE")

    @property
    def tenant(self): return self.member.organization

    def ok(self, data, **extra):
        return Response({"data": serialize(data), "simulation": True, **extra})


class AccountsView(TreasuryAPIView):
    def get(self, request, account_id=None):
        qs = TreasuryAccountService.list(self.tenant)
        if account_id: qs = qs.filter(pk=account_id)
        rows = list(qs)
        if account_id and not rows: return Response({"code": "NOT_FOUND"}, status=404)
        return self.ok(rows)


class CashView(TreasuryAPIView):
    def get(self, request, currency=None): return self.ok(list(CashPositionService.get_positions(self.tenant, currency)))


class LiquidityView(TreasuryAPIView):
    def get(self, request, currency=None): return self.ok(list(LiquidityService.get_snapshot(self.tenant, currency)))


class CollateralView(TreasuryAPIView):
    def get(self, request, asset=None): return self.ok(list(TreasuryCollateralService.inventory(self.tenant, asset)))


class MobilityPreviewView(TreasuryAPIView):
    def post(self, request):
        required = ("source_account_id", "destination_account_id", "asset", "quantity")
        if any(not request.data.get(k) for k in required): return Response({"code": "VALIDATION_ERROR"}, status=400)
        try:
            result = CollateralMobilityService.preview(self.tenant, request.data["source_account_id"], request.data["destination_account_id"], request.data["asset"], request.data["quantity"])
        except ObjectDoesNotExist: return Response({"code": "NOT_FOUND"}, status=404)
        except (ValueError, TypeError): return Response({"code": "VALIDATION_ERROR"}, status=400)
        return self.ok(result)


class FundingRequirementsView(TreasuryAPIView):
    def get(self, request, requirement_id=None):
        qs = FundingRequirement.objects.filter(tenant=self.tenant)
        if requirement_id: qs = qs.filter(pk=requirement_id)
        rows = list(qs.order_by("due_at"))
        if requirement_id and not rows: return Response({"code": "NOT_FOUND"}, status=404)
        return self.ok(rows)


class IntradayView(TreasuryAPIView):
    def get(self, request, currency=None):
        qs = IntradayFundingWindow.objects.filter(tenant=self.tenant)
        if currency: qs = qs.filter(currency=currency.upper())
        return self.ok(list(qs.order_by("-window_start")))


class ForecastView(TreasuryAPIView):
    def get(self, request, currency=None):
        qs = LiquidityForecast.objects.filter(tenant=self.tenant)
        if currency: qs = qs.filter(currency=currency.upper())
        return self.ok(list(qs.order_by("-forecast_time")))


class TransferPlansView(TreasuryAPIView):
    def get(self, request, plan_id=None):
        qs = TreasuryTransferPlan.objects.filter(tenant=self.tenant).prefetch_related("items")
        if plan_id: qs = qs.filter(pk=plan_id)
        payload = []
        for plan in qs.order_by("-created_at"):
            row = serialize(plan); row["items"] = serialize(list(plan.items.all())); payload.append(row)
        if plan_id and not payload: return Response({"code": "NOT_FOUND"}, status=404)
        return self.ok(payload)


class TransferPlanPreviewView(TreasuryAPIView):
    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        fields = ("institution_id", "currency_or_asset", "required_amount_or_quantity", "destination_account_id")
        if any(not request.data.get(k) for k in fields): return Response({"code": "VALIDATION_ERROR"}, status=400)
        command, error = command_context(request)
        if error: return error
        key, request_id, correlation_id, _ = command
        payload = {field: request.data[field] for field in fields}
        try:
            record, created = begin_command(request, tenant=self.tenant, key=key, payload=payload)
        except IdempotencyConflict:
            return Response({"code": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return replay(record)
        try:
            destination = TreasuryAccountService.get(self.tenant, request.data["destination_account_id"])
            plan = TreasuryPlanner.generate_cash_plan(self.tenant, request.data["institution_id"], request.data["currency_or_asset"], request.data["required_amount_or_quantity"], destination, key)
        except ObjectDoesNotExist:
            record.delete(); return Response({"code": "NOT_FOUND"}, status=404)
        except ValueError as exc:
            record.delete()
            if str(exc) == "IDEMPOTENCY_CONFLICT": return Response({"code": "IDEMPOTENCY_CONFLICT"}, status=409)
            return Response({"code": "VALIDATION_ERROR"}, status=400)
        except TypeError:
            record.delete(); return Response({"code": "VALIDATION_ERROR"}, status=400)
        body = {"data": serialize(plan), "simulation": True, "items": serialize(list(plan.items.all()))}
        command_audit(request, tenant=self.tenant, action="treasury.transfer_plan.command.generated", resource_type="TreasuryTransferPlan", resource_id=plan.pk, request_id=request_id, correlation_id=correlation_id)
        complete_idempotent_request(record, status=200, body=body, resource_type="treasury_transfer_plan", resource_id=plan.pk)
        return Response(body)


class SettlementFundingView(TreasuryAPIView):
    def get(self, request, settlement_id=None):
        qs = FundingRequirement.objects.filter(tenant=self.tenant, requirement_type="SETTLEMENT")
        if settlement_id: qs = qs.filter(source_ref=settlement_id)
        rows = [SettlementFundingService.evaluate(r) for r in qs.order_by("due_at")]
        if settlement_id and not rows: return Response({"code": "NOT_FOUND"}, status=404)
        return self.ok(rows)


class StressPreviewView(TreasuryAPIView):
    def post(self, request):
        if not request.data.get("institution_id") or not request.data.get("currency"):
            return Response({"code": "VALIDATION_ERROR"}, status=400)
        scenario = LiquidityStressScenario.objects.filter(code=request.data.get("scenario_code"), status="SIMULATION").first()
        if not scenario: return Response({"code": "VALIDATION_ERROR"}, status=400)
        result = LiquidityStressService.run(self.tenant, request.data.get("institution_id"), request.data.get("currency", "USD"), scenario)
        return self.ok(result)


class ReconciliationStatusView(TreasuryAPIView):
    def get(self, request):
        run = TreasuryReconciliationRun.objects.filter(tenant=self.tenant).order_by("-started_at").first()
        return self.ok(run or {"status": "NOT_RUN", "checks": list(TreasuryReconciler.CHECKS), "violations": []})


class OperatorTreasuryAPIView(TreasuryAPIView):
    operator_roles = {"treasury_viewer", "treasury_analyst", "treasury_manager", "collateral_operations", "liquidity_risk"}


class OperatorAccountsView(OperatorTreasuryAPIView, AccountsView): pass
class OperatorPlansView(OperatorTreasuryAPIView, TransferPlansView): pass


class OperatorPlanActionView(OperatorTreasuryAPIView):
    operator_roles = {"treasury_analyst", "treasury_manager"}
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request, plan_id, action):
        command, error = command_context(request, require_version=True)
        if error: return error
        key, request_id, correlation_id, expected_version = command
        plan = TreasuryTransferPlan.objects.select_for_update().filter(tenant=self.tenant, pk=plan_id).first()
        if not plan: return Response({"code": "NOT_FOUND"}, status=404)
        try:
            record, created = begin_command(request, tenant=self.tenant, key=key, payload={"plan_id": str(plan_id), "action": action, "expected_version": expected_version})
        except IdempotencyConflict: return Response({"code": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return replay(record)
        if plan.state != expected_version:
            record.delete(); return Response({"code": "VERSION_CONFLICT"}, status=409)
        if action == "simulate" and plan.state in ("VALIDATED", "APPROVED_SIMULATION"): plan.state = "SIMULATED"
        elif action == "cancel" and plan.state not in ("SIMULATED", "CANCELLED"): plan.state = "CANCELLED"
        else:
            record.delete(); return Response({"code": "CONFLICT"}, status=409)
        plan.save(update_fields=("state",))
        body = {"data": serialize(plan), "simulation": True}
        command_audit(request, tenant=self.tenant, action=f"treasury.transfer_plan.{action}", resource_type="TreasuryTransferPlan", resource_id=plan.pk, request_id=request_id, correlation_id=correlation_id, context={"state": plan.state})
        complete_idempotent_request(record, status=200, body=body, resource_type="treasury_transfer_plan", resource_id=plan.pk)
        return Response(body)


class OperatorStressScenariosView(OperatorTreasuryAPIView):
    def get(self, request): return self.ok(list(LiquidityStressScenario.objects.filter(status="SIMULATION")))


class OperatorStressRunView(OperatorTreasuryAPIView):
    operator_roles = {"treasury_analyst", "treasury_manager", "liquidity_risk"}
    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        command, error = command_context(request)
        if error: return error
        key, request_id, correlation_id, _ = command
        payload = {"institution_id": request.data.get("institution_id"), "currency": request.data.get("currency"), "scenario_code": request.data.get("scenario_code")}
        try: record, created = begin_command(request, tenant=self.tenant, key=key, payload=payload)
        except IdempotencyConflict: return Response({"code": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return replay(record)
        response = StressPreviewView.post(self, request)
        if response.status_code >= 400:
            record.delete(); return response
        resource_id = response.data["data"].get("id", "")
        command_audit(request, tenant=self.tenant, action="treasury.stress.command.completed", resource_type="LiquidityStressResult", resource_id=resource_id, request_id=request_id, correlation_id=correlation_id)
        complete_idempotent_request(record, status=response.status_code, body=response.data, resource_type="treasury_stress_result", resource_id=resource_id)
        return response


class OperatorExceptionsView(OperatorTreasuryAPIView):
    def get(self, request, exception_id=None):
        qs = TreasuryException.objects.filter(tenant=self.tenant)
        if exception_id: qs = qs.filter(pk=exception_id)
        rows = list(qs.order_by("-detected_at"))
        if exception_id and not rows:
            return Response({"code": "NOT_FOUND"}, status=404)
        return self.ok([{**serialize(item), "version": exception_version(item)} for item in rows])


class OperatorExceptionActionView(OperatorTreasuryAPIView):
    operator_roles = {"treasury_manager"}
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request, exception_id, action):
        command, error = command_context(request, require_version=True)
        if error: return error
        key, request_id, correlation_id, expected_version = command
        item = TreasuryException.objects.select_for_update().filter(tenant=self.tenant, pk=exception_id).first()
        if not item: return Response({"code": "NOT_FOUND"}, status=404)
        try: record, created = begin_command(request, tenant=self.tenant, key=key, payload={"exception_id": str(exception_id), "action": action, "expected_version": expected_version, "resolution_code": request.data.get("resolution_code")})
        except IdempotencyConflict: return Response({"code": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return replay(record)
        if exception_version(item) != expected_version:
            record.delete(); return Response({"code": "VERSION_CONFLICT"}, status=409)
        if action == "assign": item.assigned_to = request.user
        elif action == "escalate": item.severity = "CRITICAL"
        elif action == "resolve":
            if item.assigned_to_id is None or item.assigned_to_id == request.user.pk:
                record.delete(); return Response({"code": "MAKER_CHECKER_REQUIRED"}, status=409)
            item.state, item.resolved_at, item.resolution_code = "RESOLVED", timezone.now(), request.data.get("resolution_code", "SIMULATION_REVIEWED")
        else:
            record.delete(); return Response({"code": "VALIDATION_ERROR"}, status=400)
        item.save()
        body = {"data": {**serialize(item), "version": exception_version(item)}, "simulation": True}
        command_audit(request, tenant=self.tenant, action=f"treasury.exception.{action}", resource_type="TreasuryException", resource_id=item.pk, request_id=request_id, correlation_id=correlation_id, context={"state": item.state, "severity": item.severity})
        complete_idempotent_request(record, status=200, body=body, resource_type="treasury_exception", resource_id=item.pk)
        return Response(body)


class OperatorReconciliationView(OperatorTreasuryAPIView):
    def get(self, request): return self.ok(list(TreasuryReconciliationRun.objects.filter(tenant=self.tenant).order_by("-started_at")))

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        if self.member.role not in {"treasury_analyst", "treasury_manager", "liquidity_risk"} and not request.user.is_superuser: return Response({"code": "FORBIDDEN"}, status=403)
        command, error = command_context(request)
        if error: return error
        key, request_id, correlation_id, _ = command
        try: record, created = begin_command(request, tenant=self.tenant, key=key, payload={"operation": "TREASURY_RECONCILIATION"})
        except IdempotencyConflict: return Response({"code": "IDEMPOTENCY_CONFLICT"}, status=409)
        if not created: return replay(record)
        run = TreasuryReconciler.run(self.tenant)
        body = {"data": serialize(run), "simulation": True}
        command_audit(request, tenant=self.tenant, action="treasury.reconciliation.command.completed", resource_type="TreasuryReconciliationRun", resource_id=run.pk, request_id=request_id, correlation_id=correlation_id, context={"status": run.status})
        complete_idempotent_request(record, status=200, body=body, resource_type="treasury_reconciliation", resource_id=run.pk)
        return Response(body)


class OperatorEvidenceView(OperatorTreasuryAPIView):
    def get(self, request, requirement_id):
        requirement = FundingRequirement.objects.filter(tenant=self.tenant, pk=requirement_id).first()
        if not requirement: return Response({"code": "NOT_FOUND"}, status=404)
        return self.ok({"funding_requirement": requirement, "liquidity_snapshots": list(LiquiditySnapshot.objects.filter(tenant=self.tenant, currency=requirement.currency_or_asset).order_by("-as_of")[:5]), "transfer_plans": list(TreasuryTransferPlan.objects.filter(tenant=self.tenant, currency_or_asset=requirement.currency_or_asset)), "reconciliation": list(TreasuryReconciliationRun.objects.filter(tenant=self.tenant).order_by("-started_at")[:5])})
