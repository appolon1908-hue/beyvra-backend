import uuid
from decimal import Decimal

from django.forms.models import model_to_dict
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    def post(self, request):
        fields = ("institution_id", "currency_or_asset", "required_amount_or_quantity", "destination_account_id")
        if any(not request.data.get(k) for k in fields): return Response({"code": "VALIDATION_ERROR"}, status=400)
        key = request.headers.get("Idempotency-Key")
        if not key: return Response({"code": "IDEMPOTENCY_KEY_REQUIRED"}, status=400)
        try:
            destination = TreasuryAccountService.get(self.tenant, request.data["destination_account_id"])
            plan = TreasuryPlanner.generate_cash_plan(self.tenant, request.data["institution_id"], request.data["currency_or_asset"], request.data["required_amount_or_quantity"], destination, key)
        except ObjectDoesNotExist: return Response({"code": "NOT_FOUND"}, status=404)
        except ValueError as exc:
            if str(exc) == "IDEMPOTENCY_CONFLICT": return Response({"code": "IDEMPOTENCY_CONFLICT"}, status=409)
            return Response({"code": "VALIDATION_ERROR"}, status=400)
        except TypeError: return Response({"code": "VALIDATION_ERROR"}, status=400)
        return self.ok(plan, items=serialize(list(plan.items.all())))


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
    def post(self, request, plan_id, action):
        plan = TreasuryTransferPlan.objects.filter(tenant=self.tenant, pk=plan_id).first()
        if not plan: return Response({"code": "NOT_FOUND"}, status=404)
        if action == "simulate" and plan.state in ("VALIDATED", "APPROVED_SIMULATION"): plan.state = "SIMULATED"
        elif action == "cancel" and plan.state not in ("SIMULATED", "CANCELLED"): plan.state = "CANCELLED"
        else: return Response({"code": "CONFLICT"}, status=409)
        plan.save(update_fields=("state",))
        return self.ok(plan)


class OperatorStressScenariosView(OperatorTreasuryAPIView):
    def get(self, request): return self.ok(list(LiquidityStressScenario.objects.filter(status="SIMULATION")))


class OperatorStressRunView(OperatorTreasuryAPIView):
    operator_roles = {"treasury_analyst", "treasury_manager", "liquidity_risk"}
    def post(self, request): return StressPreviewView.post(self, request)


class OperatorExceptionsView(OperatorTreasuryAPIView):
    def get(self, request, exception_id=None):
        qs = TreasuryException.objects.filter(tenant=self.tenant)
        if exception_id: qs = qs.filter(pk=exception_id)
        return self.ok(list(qs.order_by("-detected_at")))


class OperatorExceptionActionView(OperatorTreasuryAPIView):
    operator_roles = {"treasury_manager"}
    def post(self, request, exception_id, action):
        item = TreasuryException.objects.filter(tenant=self.tenant, pk=exception_id).first()
        if not item: return Response({"code": "NOT_FOUND"}, status=404)
        if action == "assign": item.assigned_to = request.user
        elif action == "escalate": item.severity = "CRITICAL"
        elif action == "resolve":
            if request.data.get("maker_ref") == str(request.user.pk): return Response({"code": "MAKER_CHECKER_REQUIRED"}, status=409)
            item.state, item.resolved_at, item.resolution_code = "RESOLVED", timezone.now(), request.data.get("resolution_code", "SIMULATION_REVIEWED")
        item.save()
        return self.ok(item)


class OperatorReconciliationView(OperatorTreasuryAPIView):
    def get(self, request): return self.ok(list(TreasuryReconciliationRun.objects.filter(tenant=self.tenant).order_by("-started_at")))

    def post(self, request):
        if self.member.role not in {"treasury_analyst", "treasury_manager", "liquidity_risk"} and not request.user.is_superuser: return Response({"code": "FORBIDDEN"}, status=403)
        return self.ok(TreasuryReconciler.run(self.tenant))


class OperatorEvidenceView(OperatorTreasuryAPIView):
    def get(self, request, requirement_id):
        requirement = FundingRequirement.objects.filter(tenant=self.tenant, pk=requirement_id).first()
        if not requirement: return Response({"code": "NOT_FOUND"}, status=404)
        return self.ok({"funding_requirement": requirement, "liquidity_snapshots": list(LiquiditySnapshot.objects.filter(tenant=self.tenant, currency=requirement.currency_or_asset).order_by("-as_of")[:5]), "transfer_plans": list(TreasuryTransferPlan.objects.filter(tenant=self.tenant, currency_or_asset=requirement.currency_or_asset)), "reconciliation": list(TreasuryReconciliationRun.objects.filter(tenant=self.tenant).order_by("-started_at")[:5])})
