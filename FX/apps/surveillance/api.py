import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, serializers, status, views
from rest_framework.response import Response

from apps.foundation.services import enqueue_event
from apps.trading.api.errors import error_response
from operations.permissions import current_session_has_mfa

from .engine import evidence_hash
from .models import SurveillanceCase, SurveillanceCaseEvent, SurveillanceEvent, SurveillanceRule, TradingRestriction
from .services import audit


def _roles(user):
    return set(user.groups.values_list("name", flat=True))


class SurveillanceViewer(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_superuser or _roles(request.user) & {"surveillance_viewer", "surveillance_analyst", "surveillance_manager", "platform_admin"}))


class SurveillanceAnalyst(SurveillanceViewer):
    def has_permission(self, request, view):
        return bool(super().has_permission(request, view) and current_session_has_mfa(request) and (request.user.is_superuser or _roles(request.user) & {"surveillance_analyst", "surveillance_manager", "platform_admin"}))


class SurveillanceManager(SurveillanceViewer):
    def has_permission(self, request, view):
        return bool(super().has_permission(request, view) and current_session_has_mfa(request) and (request.user.is_superuser or _roles(request.user) & {"surveillance_manager", "platform_admin"}))


class EventSerializer(serializers.ModelSerializer):
    rule_id = serializers.UUIDField(read_only=True)
    class Meta:
        model = SurveillanceEvent
        fields = ("id", "account_ref", "instrument_id", "event_type", "severity", "detected_at", "window_start", "window_end", "rule_id", "rule_version", "policy_version", "score", "status", "evidence_hash", "evidence_safe")


class CaseSerializer(serializers.ModelSerializer):
    event_ids = serializers.SerializerMethodField()
    class Meta:
        model = SurveillanceCase
        fields = ("id", "account_ref", "case_type", "severity", "status", "assigned_to", "opened_at", "updated_at", "resolved_at", "resolution_code", "policy_version", "evidence_hash", "event_ids")
    def get_event_ids(self, obj): return [str(v) for v in obj.events.values_list("id", flat=True)]


class RestrictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradingRestriction
        fields = ("id", "scope_type", "scope_ref", "restriction_type", "effective_from", "effective_to", "status", "created_at", "updated_at")


class RuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveillanceRule
        fields = ("id", "name", "event_type", "enabled", "severity", "asset_class", "parameters_json_safe", "policy_version", "version", "effective_from", "effective_to")


class EventList(views.APIView):
    permission_classes = (SurveillanceViewer,)
    def get(self, request):
        rows = SurveillanceEvent.objects.filter(tenant_ref="default").order_by("-detected_at")[:200]
        return Response({"results": EventSerializer(rows, many=True).data})


class EventDetail(views.APIView):
    permission_classes = (SurveillanceViewer,)
    def get(self, request, event_id):
        row = SurveillanceEvent.objects.filter(id=event_id, tenant_ref="default").first()
        return Response(EventSerializer(row).data) if row else error_response(request, "RESOURCE_NOT_FOUND", 404)


class CaseList(views.APIView):
    permission_classes = (SurveillanceViewer,)
    def get(self, request):
        rows = SurveillanceCase.objects.filter(tenant_ref="default").order_by("-opened_at")[:200]
        return Response({"results": CaseSerializer(rows, many=True).data})


class CaseDetail(views.APIView):
    permission_classes = (SurveillanceViewer,)
    def get(self, request, case_id):
        row = SurveillanceCase.objects.filter(id=case_id, tenant_ref="default").first()
        return Response(CaseSerializer(row).data) if row else error_response(request, "RESOURCE_NOT_FOUND", 404)


class CaseAction(views.APIView):
    permission_classes = (SurveillanceAnalyst,)
    action = ""
    @transaction.atomic
    def post(self, request, case_id):
        row = SurveillanceCase.objects.select_for_update().filter(id=case_id, tenant_ref="default").first()
        if not row: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        reason = str(request.data.get("reason", "")).strip()
        if not reason: return error_response(request, "VALIDATION_ERROR", 400)
        if self.action == "assign": row.assigned_to = str(request.data.get("assigned_to") or request.user.pk); row.status = "IN_REVIEW"
        elif self.action == "escalate": row.status = "ESCALATED"
        elif self.action == "resolve":
            if row.severity == "CRITICAL" and not (request.user.is_superuser or "surveillance_manager" in _roles(request.user)): return error_response(request, "PERMISSION_DENIED", 403)
            row.status = "RESOLVED"; row.resolution_code = str(request.data.get("resolution_code", "REVIEW_COMPLETE"))[:64]; row.resolved_at = timezone.now()
        row.save()
        SurveillanceCaseEvent.objects.create(case=row, event_type={"assign": "CASE_ASSIGNED", "escalate": "CASE_ESCALATED", "resolve": "CASE_RESOLVED"}[self.action], actor_ref=str(request.user.pk), reason=reason, evidence_hash=evidence_hash({"status": row.status, "assigned_to": row.assigned_to, "resolution_code": row.resolution_code}), occurred_at=timezone.now())
        audit(tenant_ref=row.tenant_ref, actor_ref=request.user.pk, action=f"surveillance.case.{self.action}", resource_type="surveillance_case", resource_ref=row.id, reason=reason)
        return Response(CaseSerializer(row).data)


class AssignCase(CaseAction): action = "assign"
class EscalateCase(CaseAction): action = "escalate"
class ResolveCase(CaseAction): action = "resolve"


class RestrictionList(views.APIView):
    permission_classes = (SurveillanceViewer,)
    def get(self, request):
        rows = TradingRestriction.objects.filter(tenant_ref="default").order_by("-created_at")[:200]
        return Response({"results": RestrictionSerializer(rows, many=True).data})
    @transaction.atomic
    def post(self, request):
        if not SurveillanceManager().has_permission(request, self): return error_response(request, "PERMISSION_DENIED", 403)
        required = ("scope_type", "scope_ref", "restriction_type", "reason")
        if any(not request.data.get(key) for key in required): return error_response(request, "VALIDATION_ERROR", 400)
        try:
            row = TradingRestriction(tenant_ref="default", scope_type=request.data["scope_type"], scope_ref=str(request.data["scope_ref"]), restriction_type=request.data["restriction_type"], reason_code="INTERNAL_REVIEW", effective_from=timezone.now(), effective_to=request.data.get("effective_to"), created_by=str(request.user.pk), status="PENDING")
            row.full_clean(); row.save()
        except Exception: return error_response(request, "VALIDATION_ERROR", 400)
        audit(tenant_ref="default", actor_ref=request.user.pk, action="surveillance.restriction.requested", resource_type="trading_restriction", resource_ref=row.id, reason=str(request.data["reason"]))
        return Response(RestrictionSerializer(row).data, status=status.HTTP_201_CREATED)


class ApproveRestriction(views.APIView):
    permission_classes = (SurveillanceManager,)
    @transaction.atomic
    def post(self, request, restriction_id):
        row = TradingRestriction.objects.select_for_update().filter(id=restriction_id, tenant_ref="default", status="PENDING").first()
        if not row: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        if row.created_by == str(request.user.pk): return error_response(request, "SELF_APPROVAL_FORBIDDEN", 403)
        row.approved_by = str(request.user.pk); row.status = "ACTIVE"; row.full_clean(); row.save()
        audit(tenant_ref=row.tenant_ref, actor_ref=request.user.pk, action="surveillance.restriction.approved", resource_type="trading_restriction", resource_ref=row.id, reason=str(request.data.get("reason", "independent approval")))
        enqueue_event(aggregate_type="trading_restriction", aggregate_id=row.id, event_type="regulatory.surveillance.restriction.applied.v1", payload={"restriction_id": str(row.id), "scope_type": row.scope_type, "scope_ref": row.scope_ref}, tenant_ref=row.tenant_ref)
        return Response(RestrictionSerializer(row).data)


class RemoveRestriction(views.APIView):
    permission_classes = (SurveillanceManager,)
    @transaction.atomic
    def post(self, request, restriction_id):
        row = TradingRestriction.objects.select_for_update().filter(id=restriction_id, tenant_ref="default", status="ACTIVE").first()
        if not row: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        if row.approved_by == str(request.user.pk): return error_response(request, "SELF_APPROVAL_FORBIDDEN", 403)
        reason = str(request.data.get("reason", "")).strip()
        if not reason: return error_response(request, "VALIDATION_ERROR", 400)
        row.status = "REMOVED"; row.effective_to = timezone.now(); row.save()
        audit(tenant_ref=row.tenant_ref, actor_ref=request.user.pk, action="surveillance.restriction.removed", resource_type="trading_restriction", resource_ref=row.id, reason=reason)
        enqueue_event(aggregate_type="trading_restriction", aggregate_id=row.id, event_type="regulatory.surveillance.restriction.removed.v1", payload={"restriction_id": str(row.id)}, tenant_ref=row.tenant_ref)
        return Response(RestrictionSerializer(row).data)


class RuleList(views.APIView):
    permission_classes = (SurveillanceViewer,)
    def get(self, request): return Response({"results": RuleSerializer(SurveillanceRule.objects.order_by("name", "-version"), many=True).data})
