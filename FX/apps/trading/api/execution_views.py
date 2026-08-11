from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trading.execution_authority import preview_route, record_quality, seed_safe_authorities, serialize_quality, set_provider_halt
from apps.trading.models import ExecutionProviderRecord, ExecutionQualityReport, ExecutionRoutingDecision, ExecutionVenue, TradingOrder
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
        seed_safe_authorities()
        rows = ExecutionProviderRecord.objects.exclude(mode="LIVE").order_by("provider_id")
        return Response({"results": [{"provider_id": x.provider_id, "name": x.display_name, "mode": x.mode, "enabled": x.enabled,
            "health": x.health, "capabilities": x.capabilities, "asset_classes": x.supported_asset_classes,
            "order_types": x.supported_order_types, "venues": x.supported_venues} for x in rows], "live_broker_routing_enabled": False})


class VenuesView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        seed_safe_authorities()
        return Response({"results": [{"venue_id": x.venue_id, "name": x.display_name, "asset_classes": x.asset_classes,
            "order_types": x.order_types, "active": x.active, "delayed": x.delayed} for x in ExecutionVenue.objects.order_by("venue_id")]})


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


class OperatorRoutesView(APIView):
    permission_classes = (IsAdminUser,)
    def get(self, request):
        return Response({"results": [{"decision_id": str(x.decision_id), "order_id": str(x.order_id), "status": x.status,
            "provider_id": x.selected_provider_id, "venue_id": x.selected_venue_id, "policy_version": x.policy_version} for x in ExecutionRoutingDecision.objects.order_by("-created_at")[:200]]})


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
