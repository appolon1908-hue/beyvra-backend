import uuid

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trading.execution_authority import preview_route, serialize_quality, set_provider_halt
from apps.trading.execution_control.capabilities import seed_fixture_capabilities
from apps.trading.execution_control.health import ProviderHealthService
from apps.trading.execution_control.reconciliation import ExecutionReconciler
from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import IdempotencyConflict, begin_idempotent_request, complete_idempotent_request
from apps.trading.models import ExecutionGovernanceChange, ExecutionProviderRecord, ExecutionQualityReport, ExecutionReconciliationRun, ExecutionRoutingDecision, ExecutionVenue, TradingOrder, UnknownExecutionOutcome
from .errors import error_response


COMMAND_PARAMETERS = [
    OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Request-ID", str, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Correlation-ID", str, OpenApiParameter.HEADER, required=False),
]
VERSIONED_COMMAND_PARAMETERS = [*COMMAND_PARAMETERS, OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)]
PAPER_ENABLE_REQUEST = inline_serializer("ExecutionPaperEnableCommand", {"reason": serializers.CharField()})
PAPER_ENABLE_RESPONSE = inline_serializer("ExecutionPaperEnableResult", {
    "change_id": serializers.UUIDField(), "provider_id": serializers.CharField(), "status": serializers.CharField(),
    "enabled": serializers.BooleanField(), "maker_checker_required": serializers.BooleanField(required=False),
    "mode": serializers.CharField(required=False), "live": serializers.BooleanField(required=False), "version": serializers.CharField(),
})
EXECUTION_RECONCILIATION_RESPONSE = inline_serializer("ExecutionReconciliationCommandResult", {
    "id": serializers.UUIDField(), "status": serializers.CharField(), "critical_count": serializers.IntegerField(),
})


def _fail(request, exc):
    code = str(exc)
    status = 503 if code.endswith("DISABLED") else 422 if code == "VALIDATION_ERROR" else 404
    return error_response(request, code, status)


def _bounded_limit(request, default=50, maximum=200):
    try:
        return max(1, min(int(request.query_params.get("limit", default)), maximum))
    except (TypeError, ValueError):
        return default


def _command_context(request, *, require_reason=False, require_version=False):
    key = request.headers.get("Idempotency-Key", "").strip()
    request_id = request.headers.get("X-Request-ID", "").strip()
    reason = str(request.data.get("reason", "")).strip()
    expected_version = request.headers.get("If-Match", "").strip()
    if not key or len(key) > 255 or not request_id or len(request_id) > 128 or (require_reason and not reason):
        return None, error_response(request, "VALIDATION_ERROR", 400, {"required": ["Idempotency-Key", "X-Request-ID"] + (["reason"] if require_reason else [])})
    if require_version and not expected_version:
        return None, error_response(request, "PRECONDITION_REQUIRED", 428, {"required": ["If-Match"]})
    raw_correlation = request.headers.get("X-Correlation-ID") or request_id
    try:
        correlation_id = uuid.UUID(raw_correlation)
    except (TypeError, ValueError):
        return None, error_response(request, "VALIDATION_ERROR", 400, {"invalid": ["X-Correlation-ID"]})
    return (key, request_id, correlation_id, reason, expected_version), None


def _version(row):
    return row.updated_at.isoformat().replace("+00:00", "Z")


def _begin_command(request, *, key, payload):
    return begin_idempotent_request(
        key=key, tenant_ref="platform", actor_ref=request.user.pk, endpoint=request.path,
        method=request.method, request_data={"api_version": "v1", **payload},
    )


def _replay(record):
    if record.response_status is None or record.response_body is None:
        return Response({"error": {"code": "COMMAND_IN_PROGRESS", "message": "Command result is not yet available."}}, status=409)
    return Response(record.response_body, status=record.response_status)


def _audit(request, *, action, resource_type, resource_id, request_id, correlation_id, reason, context=None):
    ApplicationAuditEvent.objects.create(
        actor_ref=str(request.user.pk), action=action, resource_type=resource_type, resource_id=str(resource_id),
        request_id=request_id, correlation_id=correlation_id, context=context or {}, reason=reason[:255], occurred_at=timezone.now(),
    )


def _quality_rows(request, *, customer=False):
    rows=ExecutionQualityReport.objects.select_related("order","routing_decision")
    if customer: rows=rows.filter(order__subject_ref=str(request.user.pk),order__tenant_ref="default")
    filters={"provider":"routing_decision__selected_provider_id","venue":"routing_decision__selected_venue_id","instrument":"order__instrument_id","mode":"routing_decision__mode","quality_outcome":"quality_state"}
    for query,field in filters.items():
        value=request.query_params.get(query)
        if value: rows=rows.filter(**{field:value})
    if request.query_params.get("published_after"): rows=rows.filter(created_at__gte=request.query_params["published_after"])
    if request.query_params.get("published_before"): rows=rows.filter(created_at__lte=request.query_params["published_before"])
    return rows.order_by("-created_at","-report_id")[:_bounded_limit(request)]


def _has_execution_role(user, *roles):
    return bool(user and user.is_authenticated and (user.is_superuser or user.groups.filter(name__in=roles).exists()))


class IsExecutionViewer(BasePermission):
    def has_permission(self, request, view):
        return _has_execution_role(request.user, "execution_viewer", "execution_operator", "execution_manager")


class IsExecutionOperator(BasePermission):
    def has_permission(self, request, view):
        return _has_execution_role(request.user, "execution_operator", "execution_manager")


class IsExecutionManager(BasePermission):
    def has_permission(self, request, view):
        return _has_execution_role(request.user, "execution_manager")


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
            "market_snapshot_hash": row.market_snapshot_hash, "request_hash": row.request_hash,"revision":row.revision,"supersedes":str(row.supersedes_id) if row.supersedes_id else None})


class QualityView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, order_id):
        order = TradingOrder.objects.filter(pk=order_id, subject_ref=str(request.user.pk), tenant_ref="default", simulation=True).first()
        if not order: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        row = ExecutionQualityReport.objects.filter(order=order).order_by("-revision").first()
        return Response(serialize_quality(row)) if row else error_response(request, "EXECUTION_QUALITY_NOT_AVAILABLE", 404)


class ReportsView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        rows = _quality_rows(request,customer=True)
        return Response({"results": [serialize_quality(x) for x in rows]})


class ReportView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, report_id):
        row = ExecutionQualityReport.objects.filter(pk=report_id, order__subject_ref=str(request.user.pk), order__tenant_ref="default").first()
        return Response(serialize_quality(row)) if row else error_response(request, "RESOURCE_NOT_FOUND", 404)


class OperatorProvidersView(CapabilitiesView): permission_classes = (IsExecutionViewer,)

class OperatorProviderDetailView(CapabilityDetailView): permission_classes=(IsExecutionViewer,)
class OperatorProviderCapabilityView(CapabilityDetailView): permission_classes=(IsExecutionViewer,)
class OperatorVenuesView(VenuesView): permission_classes=(IsExecutionViewer,)

class OperatorProviderHealthView(APIView):
    permission_classes=(IsExecutionViewer,)
    def get(self,request,provider_code):
        seed_fixture_capabilities(); x=ExecutionProviderRecord.objects.filter(pk=provider_code).first()
        if not x:return error_response(request,"RESOURCE_NOT_FOUND",404)
        service=ProviderHealthService(); row=getattr(x,"health_record",None)
        return Response({"provider_id":x.provider_id,"state":service.evaluate(x),"routable":service.is_routable(x),"circuit_state":row.circuit_state if row else "CLOSED"})


class OperatorRoutesView(APIView):
    permission_classes = (IsExecutionViewer,)
    def get(self, request):
        return Response({"results": [{"decision_id": str(x.decision_id), "order_id": str(x.order_id), "status": x.status,
            "provider_id": x.selected_provider_id, "venue_id": x.selected_venue_id, "policy_version": x.policy_version} for x in ExecutionRoutingDecision.objects.order_by("-created_at","-decision_id")[:_bounded_limit(request)]]})

class OperatorRouteDetailView(APIView):
    permission_classes=(IsExecutionViewer,)
    def get(self,request,order_id):
        x=ExecutionRoutingDecision.objects.filter(order_id=order_id).order_by("-created_at").first()
        if not x:return error_response(request,"RESOURCE_NOT_FOUND",404)
        return Response({"decision_id":str(x.decision_id),"order_id":str(x.order_id),"status":x.status,"provider_id":x.selected_provider_id,
            "venue_id":x.selected_venue_id,"policy_version":x.policy_version,"evidence_hash":x.evidence_hash,"candidates":x.candidate_evidence,"exclusions":x.exclusion_reasons})


class OperatorQualityView(APIView):
    permission_classes = (IsExecutionViewer,)
    def get(self, request): return Response({"results": [serialize_quality(x) for x in _quality_rows(request)]})


class OperatorProviderControlView(APIView):
    permission_classes = (IsExecutionOperator,)
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
    permission_classes=(IsExecutionManager,)
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS, request=PAPER_ENABLE_REQUEST, responses={200: PAPER_ENABLE_RESPONSE, 202: PAPER_ENABLE_RESPONSE})
    @transaction.atomic
    def post(self,request,provider_id):
        command,error=_command_context(request,require_reason=True,require_version=True)
        if error:return error
        key,request_id,correlation_id,reason,expected_version=command
        x=ExecutionProviderRecord.objects.select_for_update().filter(pk=provider_id,mode="PAPER",live_supported=False).first()
        if not x:return error_response(request,"RESOURCE_NOT_FOUND",404)
        if x.governance_state not in {"PAPER_APPROVED","PAPER_TECHNICALLY_CERTIFIED"}:return error_response(request,"PROVIDER_NOT_APPROVED",409)
        try:
            record,created=_begin_command(request,key=key,payload={"provider_id":x.provider_id,"action":"PAPER_ENABLE","reason":reason,"expected_version":expected_version})
        except IdempotencyConflict:return error_response(request,"IDEMPOTENCY_CONFLICT",409)
        if not created:return _replay(record)
        if expected_version!=_version(x):
            record.delete();return error_response(request,"VERSION_CONFLICT",409)
        pending=ExecutionGovernanceChange.objects.select_for_update().filter(provider=x,action="PAPER_ENABLE",status="PENDING").first()
        actor_ref=str(request.user.pk)
        if not pending:
            pending=ExecutionGovernanceChange.objects.create(provider=x,action="PAPER_ENABLE",requested_by_ref=actor_ref,reason=reason)
            body={"change_id":str(pending.id),"provider_id":x.provider_id,"status":"PENDING","enabled":x.enabled,"maker_checker_required":True,"version":_version(x)}
            _audit(request,action="execution.provider.paper_enable_requested",resource_type="execution_provider",resource_id=x.provider_id,request_id=request_id,correlation_id=correlation_id,reason=reason,context={"change_id":str(pending.id),"mode":"PAPER"})
            complete_idempotent_request(record,status=202,body=body,resource_type="execution_governance_change",resource_id=pending.pk)
            return Response(body,status=202)
        if pending.requested_by_ref==actor_ref:
            record.delete();return error_response(request,"INDEPENDENT_REVIEW_REQUIRED",409)
        pending.reviewed_by_ref=actor_ref;pending.reviewed_at=timezone.now();pending.status="APPROVED";pending.save(update_fields=("reviewed_by_ref","reviewed_at","status"))
        x.enabled=True;x.save(update_fields=("enabled","updated_at"))
        body={"change_id":str(pending.id),"provider_id":x.provider_id,"mode":"PAPER","enabled":True,"live":False,"status":"APPROVED","version":_version(x)}
        _audit(request,action="execution.provider.paper_enabled",resource_type="execution_provider",resource_id=x.provider_id,request_id=request_id,correlation_id=correlation_id,reason=reason,context={"mode":"PAPER","change_id":str(pending.id),"maker_ref":pending.requested_by_ref,"checker_ref":actor_ref})
        complete_idempotent_request(record,status=200,body=body,resource_type="execution_provider",resource_id=x.pk)
        return Response(body)

class OperatorUnknownView(APIView):
    permission_classes=(IsExecutionViewer,)
    def get(self,request):
        rows=UnknownExecutionOutcome.objects.select_related("execution").order_by("-created_at")[:200]
        return Response({"results":[{"id":str(x.id),"execution_id":str(x.execution_id),"state":x.state,"classification":x.classification,
            "lookup_attempts":x.lookup_attempts,"created_at":x.created_at.isoformat()} for x in rows]})

class OperatorUnknownReconcileView(APIView):
    permission_classes=(IsExecutionOperator,)
    def post(self,request,outcome_id):
        row=UnknownExecutionOutcome.objects.filter(pk=outcome_id).first()
        if not row:return error_response(request,"RESOURCE_NOT_FOUND",404)
        if row.state=="RESOLVED":return Response({"id":str(row.id),"state":row.state,"retry_allowed":False,"failover_allowed":False})
        return error_response(request,"PROVIDER_LOOKUP_REQUIRED",409)

class OperatorReconciliationView(APIView):
    permission_classes=(IsExecutionOperator,)
    def get(self,request):
        return Response({"checks":ExecutionReconciler().inspect(),"runs":[{"id":str(x.id),"status":x.status,"critical_count":x.critical_count,
            "completed_at":x.completed_at.isoformat()} for x in ExecutionReconciliationRun.objects.order_by("-completed_at")[:20]]})
    @extend_schema(parameters=COMMAND_PARAMETERS, request=None, responses={201: EXECUTION_RECONCILIATION_RESPONSE})
    @transaction.atomic
    def post(self,request):
        command,error=_command_context(request)
        if error:return error
        key,request_id,correlation_id,_,_=command
        try:record,created=_begin_command(request,key=key,payload={"operation":"EXECUTION_RECONCILIATION"})
        except IdempotencyConflict:return error_response(request,"IDEMPOTENCY_CONFLICT",409)
        if not created:return _replay(record)
        row=ExecutionReconciler().run();body={"id":str(row.id),"status":row.status,"critical_count":row.critical_count}
        _audit(request,action="execution.reconciliation.completed",resource_type="execution_reconciliation",resource_id=row.pk,request_id=request_id,correlation_id=correlation_id,reason="operator reconciliation",context={"status":row.status,"critical_count":row.critical_count})
        complete_idempotent_request(record,status=201,body=body,resource_type="execution_reconciliation",resource_id=row.pk)
        return Response(body,status=201)
