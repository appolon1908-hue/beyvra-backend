from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trading.execution_authority import preview_route, record_quality, seed_safe_authorities, serialize_quality, set_provider_halt
from apps.trading.execution_control.capabilities import seed_fixture_capabilities
from apps.trading.execution_control.health import ProviderHealthService
from apps.trading.execution_control.reconciliation import ExecutionReconciler
from apps.trading.execution_control.recovery import ExecutionRecoveryService
from apps.trading.models import ExecutionProviderRecord, ExecutionQualityReport, ExecutionReconciliationRun, ExecutionRoutingDecision, ExecutionVenue, TradingOrder, UnknownExecutionOutcome
from .errors import error_response


def _fail(request, exc):
    code = str(exc)
    status = 503 if code.endswith("DISABLED") else 422 if code == "VALIDATION_ERROR" else 404
    return error_response(request, code, status)


class ExecutionPreviewView(APIView):
    permission_classes = (IsAuthenticated,)
    def post(self, request):
        try: return Response(preview_route(request.user, request.data))
        except ValueError as exc: return _fail(request, exc)


class CapabilitiesView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        seed_fixture_capabilities()
        rows = ExecutionProviderRecord.objects.exclude(mode="LIVE").order_by("provider_id")
        return Response({"results": [{"provider_id": x.provider_id, "name": x.display_name, "mode": x.mode, "enabled": x.enabled,
            "health": x.health, "capabilities": x.capabilities, "asset_classes": x.supported_asset_classes,
            "order_types": x.supported_order_types, "venues": x.supported_venues} for x in rows], "live_broker_routing_enabled": False})


class CapabilityDetailView(APIView):
    permission_classes=(IsAuthenticated,)
    def get(self,request,provider_code):
        seed_fixture_capabilities(); x=ExecutionProviderRecord.objects.exclude(mode="LIVE").filter(pk=provider_code).first()
        if not x:return error_response(request,"RESOURCE_NOT_FOUND",404)
        return Response({"provider_id":x.provider_id,"name":x.display_name,"mode":x.mode,"health":x.health,"asset_classes":x.supported_asset_classes,
            "order_types":x.supported_order_types,"capabilities":[{"asset_class":c.asset_class,"venue_id":c.venue_id,"type":c.capability_type,"source":c.source,
            "source_version":c.source_version,"verified_at":c.verified_at.isoformat()} for c in x.capability_records.filter(enabled=True).order_by("asset_class","capability_type")],"live_supported":False})


class VenuesView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        seed_fixture_capabilities()
        return Response({"results": [{"venue_id": x.venue_id, "name": x.display_name, "asset_classes": x.asset_classes,
            "order_types": x.order_types, "active": x.active, "delayed": x.delayed} for x in ExecutionVenue.objects.order_by("venue_id")]})


class VenueDetailView(APIView):
    permission_classes=(IsAuthenticated,)
    def get(self,request,venue_id):
        seed_fixture_capabilities(); x=ExecutionVenue.objects.filter(pk=venue_id).first()
        if not x:return error_response(request,"RESOURCE_NOT_FOUND",404)
        return Response({"venue_id":x.venue_id,"name":x.display_name,"venue_type":x.venue_type,"timezone":x.timezone,"status":x.status,
            "routing_enabled":x.routing_enabled,"paper_supported":x.paper_supported,"asset_classes":x.asset_classes,"order_types":x.order_types})


class ProviderStatusView(APIView):
    permission_classes=(IsAuthenticated,)
    def get(self,request):
        seed_fixture_capabilities(); service=ProviderHealthService()
        return Response({"results":[{"provider_id":x.provider_id,"mode":x.mode,"state":service.evaluate(x),"routable":service.is_routable(x)} for x in ExecutionProviderRecord.objects.exclude(mode="LIVE").order_by("provider_id")]})


class RouteView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, order_id):
        row = ExecutionRoutingDecision.objects.filter(order_id=order_id, subject_ref=str(request.user.pk), tenant_ref="default").order_by("-created_at").first()
        if not row: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        return Response({"decision_id": str(row.decision_id), "order_id": str(row.order_id), "status": row.status,
            "mode": row.mode, "selected_provider_id": row.selected_provider_id or None, "selected_venue_id": row.selected_venue_id or None,
            "policy_version": row.policy_version, "candidates": row.candidate_evidence, "exclusions": row.exclusion_reasons,
            "market_snapshot_hash": row.market_snapshot_hash, "request_hash": row.request_hash})


class QualityView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, order_id):
        order = TradingOrder.objects.filter(pk=order_id, subject_ref=str(request.user.pk), tenant_ref="default", simulation=True).first()
        if not order: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        try: return Response(serialize_quality(record_quality(order)))
        except ValueError as exc: return _fail(request, exc)


class ReportsView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        rows = ExecutionQualityReport.objects.filter(order__subject_ref=str(request.user.pk), order__tenant_ref="default").order_by("-created_at")
        return Response({"results": [serialize_quality(x) for x in rows]})


class ReportView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, report_id):
        row = ExecutionQualityReport.objects.filter(pk=report_id, order__subject_ref=str(request.user.pk), order__tenant_ref="default").first()
        return Response(serialize_quality(row)) if row else error_response(request, "RESOURCE_NOT_FOUND", 404)


class OperatorProvidersView(CapabilitiesView): permission_classes = (IsAdminUser,)

class OperatorProviderDetailView(CapabilityDetailView): permission_classes=(IsAdminUser,)
class OperatorProviderCapabilityView(CapabilityDetailView): permission_classes=(IsAdminUser,)
class OperatorVenuesView(VenuesView): permission_classes=(IsAdminUser,)

class OperatorProviderHealthView(APIView):
    permission_classes=(IsAdminUser,)
    def get(self,request,provider_code):
        seed_fixture_capabilities(); x=ExecutionProviderRecord.objects.filter(pk=provider_code).first()
        if not x:return error_response(request,"RESOURCE_NOT_FOUND",404)
        service=ProviderHealthService(); row=getattr(x,"health_record",None)
        return Response({"provider_id":x.provider_id,"state":service.evaluate(x),"routable":service.is_routable(x),"circuit_state":row.circuit_state if row else "CLOSED"})


class OperatorRoutesView(APIView):
    permission_classes = (IsAdminUser,)
    def get(self, request):
        return Response({"results": [{"decision_id": str(x.decision_id), "order_id": str(x.order_id), "status": x.status,
            "provider_id": x.selected_provider_id, "venue_id": x.selected_venue_id, "policy_version": x.policy_version} for x in ExecutionRoutingDecision.objects.order_by("-created_at")[:200]]})

class OperatorRouteDetailView(APIView):
    permission_classes=(IsAdminUser,)
    def get(self,request,order_id):
        x=ExecutionRoutingDecision.objects.filter(order_id=order_id).order_by("-created_at").first()
        if not x:return error_response(request,"RESOURCE_NOT_FOUND",404)
        return Response({"decision_id":str(x.decision_id),"order_id":str(x.order_id),"status":x.status,"provider_id":x.selected_provider_id,
            "venue_id":x.selected_venue_id,"policy_version":x.policy_version,"evidence_hash":x.evidence_hash,"candidates":x.candidate_evidence,"exclusions":x.exclusion_reasons})


class OperatorQualityView(APIView):
    permission_classes = (IsAdminUser,)
    def get(self, request): return Response({"results": [serialize_quality(x) for x in ExecutionQualityReport.objects.order_by("-created_at")[:200]]})


class OperatorProviderControlView(APIView):
    permission_classes = (IsAdminUser,)
    halted = True
    def post(self, request, provider_id):
        reason = str(request.data.get("reason") or "")
        if not reason: return error_response(request, "VALIDATION_ERROR", 422)
        try:
            row = set_provider_halt(request.user, provider_id, self.halted, reason)
            return Response({"provider_id": row.provider_id, "mode": row.mode, "health": row.health, "enabled": row.enabled})
        except (ExecutionProviderRecord.DoesNotExist, ValueError) as exc: return _fail(request, exc)


class OperatorProviderResumeView(OperatorProviderControlView): halted = False

class OperatorProviderPaperEnableView(APIView):
    permission_classes=(IsAdminUser,)
    def post(self,request,provider_id):
        x=ExecutionProviderRecord.objects.filter(pk=provider_id,mode="PAPER",live_supported=False).first()
        if not x:return error_response(request,"RESOURCE_NOT_FOUND",404)
        if x.governance_state not in {"PAPER_APPROVED","PAPER_TECHNICALLY_CERTIFIED"}:return error_response(request,"PROVIDER_NOT_APPROVED",409)
        x.enabled=True;x.save(update_fields=("enabled","updated_at"));return Response({"provider_id":x.provider_id,"mode":"PAPER","enabled":True,"live":False})

class OperatorUnknownView(APIView):
    permission_classes=(IsAdminUser,)
    def get(self,request):
        rows=UnknownExecutionOutcome.objects.select_related("execution").order_by("-created_at")[:200]
        return Response({"results":[{"id":str(x.id),"execution_id":str(x.execution_id),"state":x.state,"classification":x.classification,
            "lookup_attempts":x.lookup_attempts,"created_at":x.created_at.isoformat()} for x in rows]})

class OperatorUnknownReconcileView(APIView):
    permission_classes=(IsAdminUser,)
    def post(self,request,outcome_id):
        row=UnknownExecutionOutcome.objects.filter(pk=outcome_id).first()
        if not row:return error_response(request,"RESOURCE_NOT_FOUND",404)
        evidence=str(request.data.get("evidence_hash") or "")
        if len(evidence)!=64:return error_response(request,"VALIDATION_ERROR",422)
        row=ExecutionRecoveryService().resolve_unknown(row,lambda _: {"evidence_hash":evidence})
        return Response({"id":str(row.id),"state":row.state,"retry_allowed":False,"failover_allowed":False})

class OperatorReconciliationView(APIView):
    permission_classes=(IsAdminUser,)
    def get(self,request):
        return Response({"checks":ExecutionReconciler().inspect(),"runs":[{"id":str(x.id),"status":x.status,"critical_count":x.critical_count,
            "completed_at":x.completed_at.isoformat()} for x in ExecutionReconciliationRun.objects.order_by("-completed_at")[:20]]})
    def post(self,request):
        row=ExecutionReconciler().run(); return Response({"id":str(row.id),"status":row.status,"critical_count":row.critical_count},status=201)
