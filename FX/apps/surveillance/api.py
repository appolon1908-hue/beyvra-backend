import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, serializers, status, views
from rest_framework.response import Response

from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import IdempotencyConflict, begin_idempotent_request, complete_idempotent_request, enqueue_event
from apps.trading.api.errors import error_response

from .engine import evidence_hash
from .models import SurveillanceCase, SurveillanceCaseEvent, SurveillanceEvent, SurveillanceRule, TradingRestriction
from .services import audit


def _roles(user):
    return set(user.groups.values_list("name", flat=True))


COMMAND_PARAMETERS = [OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True), OpenApiParameter("X-Request-ID", str, OpenApiParameter.HEADER, required=True)]
VERSIONED_COMMAND_PARAMETERS = [*COMMAND_PARAMETERS, OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True, description="Resource version returned by the API.")]


def _command_headers(request, versioned=False):
    key = request.headers.get("Idempotency-Key", "")
    request_id = request.headers.get("X-Request-ID", "")
    version = request.headers.get("If-Match", "") if versioned else None
    return (key, request_id[:128], version) if key and request_id and (not versioned or version) else (None, None, None)


def _correlation(request):
    raw = str(getattr(request, "correlation_id", "") or uuid.uuid4())
    try: return uuid.UUID(raw)
    except ValueError: return uuid.uuid5(uuid.NAMESPACE_URL, raw)


def _application_audit(request, *, request_id, action, resource_type, resource_id, reason, context=None):
    return ApplicationAuditEvent.objects.create(actor_ref=str(request.user.pk), action=action, resource_type=resource_type, resource_id=str(resource_id), request_id=request_id, correlation_id=_correlation(request), context=context or {}, reason=reason[:255], occurred_at=timezone.now())


class SurveillanceViewer(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_superuser or _roles(request.user) & {"surveillance_viewer", "surveillance_analyst", "surveillance_manager", "platform_admin"}))


class SurveillanceAnalyst(SurveillanceViewer):
    def has_permission(self, request, view):
        return bool(super().has_permission(request, view) and (request.user.is_superuser or _roles(request.user) & {"surveillance_analyst", "surveillance_manager", "platform_admin"}))


class SurveillanceManager(SurveillanceViewer):
    def has_permission(self, request, view):
        return bool(super().has_permission(request, view) and (request.user.is_superuser or _roles(request.user) & {"surveillance_manager", "platform_admin"}))


class EventSerializer(serializers.ModelSerializer):
    rule_id = serializers.UUIDField(read_only=True)
    class Meta:
        model = SurveillanceEvent
        fields = ("id", "account_ref", "instrument_id", "event_type", "severity", "detected_at", "window_start", "window_end", "rule_id", "rule_version", "policy_version", "score", "status", "evidence_hash", "evidence_safe")


class CaseSerializer(serializers.ModelSerializer):
    event_ids = serializers.SerializerMethodField()
    version = serializers.SerializerMethodField()
    class Meta:
        model = SurveillanceCase
        fields = ("id", "account_ref", "case_type", "severity", "status", "assigned_to", "opened_at", "updated_at", "version", "resolved_at", "resolution_code", "policy_version", "evidence_hash", "event_ids")
    def get_event_ids(self, obj): return [str(v) for v in obj.events.values_list("id", flat=True)]
    def get_version(self, obj): return obj.updated_at.isoformat()


class RestrictionSerializer(serializers.ModelSerializer):
    version = serializers.SerializerMethodField()
    class Meta:
        model = TradingRestriction
        fields = ("id", "scope_type", "scope_ref", "restriction_type", "effective_from", "effective_to", "status", "created_at", "updated_at", "version")
    def get_version(self, obj): return obj.updated_at.isoformat()


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
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    def post(self, request, case_id):
        row = SurveillanceCase.objects.filter(id=case_id, tenant_ref="default").first()
        if not row: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        reason = str(request.data.get("reason", "")).strip()
        key, request_id, expected_version = _command_headers(request, versioned=True)
        if not reason or not key: return error_response(request, "VALIDATION_ERROR", 422, {"required": ["Idempotency-Key", "X-Request-ID", "If-Match", "reason"]})
        assigned_to = str(request.data.get("assigned_to") or request.user.pk)
        resolution_code = str(request.data.get("resolution_code", "REVIEW_COMPLETE"))[:64]
        if self.action == "resolve" and row.severity == "CRITICAL" and not (request.user.is_superuser or "surveillance_manager" in _roles(request.user)): return error_response(request, "PERMISSION_DENIED", 403)
        try:
            with transaction.atomic():
                row = SurveillanceCase.objects.select_for_update().get(pk=row.pk)
                record, fresh = begin_idempotent_request(key=key, tenant_ref=row.tenant_ref, actor_ref=request.user.pk,
                    endpoint=f"/api/v1/operator/surveillance/cases/{row.pk}/{self.action}", method="POST",
                    request_data={"case_id": str(row.pk), "action": self.action, "reason": reason, "assigned_to": assigned_to, "resolution_code": resolution_code, "expected_version": expected_version})
                if not fresh and record.response_body is not None: return Response(record.response_body, status=record.response_status)
                if row.updated_at.isoformat() != expected_version: raise ValueError("VERSION_CONFLICT")
                if self.action == "assign":
                    if row.status not in ("OPEN", "ESCALATED"): raise ValueError("INVALID_CASE_TRANSITION")
                    assignee = get_user_model().objects.filter(pk=assigned_to).first()
                    if not assignee or not (assignee.is_superuser or _roles(assignee) & {"surveillance_analyst", "surveillance_manager", "platform_admin"}): raise ValueError("INVALID_CASE_ASSIGNEE")
                    row.assigned_to = assigned_to; row.status = "IN_REVIEW"
                elif self.action == "escalate":
                    if row.status not in ("OPEN", "IN_REVIEW"): raise ValueError("INVALID_CASE_TRANSITION")
                    row.status = "ESCALATED"
                elif self.action == "resolve":
                    if row.status not in ("OPEN", "IN_REVIEW", "ESCALATED", "RESTRICTED"): raise ValueError("INVALID_CASE_TRANSITION")
                    if row.severity == "CRITICAL" and row.assigned_to == str(request.user.pk): raise ValueError("SELF_APPROVAL_FORBIDDEN")
                    row.status = "RESOLVED"; row.resolution_code = resolution_code; row.resolved_at = timezone.now()
                row.save()
                timeline = SurveillanceCaseEvent.objects.create(case=row, event_type={"assign": "CASE_ASSIGNED", "escalate": "CASE_ESCALATED", "resolve": "CASE_RESOLVED"}[self.action], actor_ref=str(request.user.pk), reason=reason, evidence_hash=evidence_hash({"status": row.status, "assigned_to": row.assigned_to, "resolution_code": row.resolution_code}), occurred_at=timezone.now())
                audit(tenant_ref=row.tenant_ref, actor_ref=request.user.pk, action=f"surveillance.case.{self.action}", resource_type="surveillance_case", resource_ref=row.id, reason=reason)
                body = CaseSerializer(row).data
                _application_audit(request, request_id=request_id, action=f"surveillance.case.{self.action}", resource_type="surveillance_case", resource_id=row.pk, reason=reason, context={"timeline_event_id": str(timeline.pk), "status": row.status})
                complete_idempotent_request(record, status=200, body=body, resource_type="surveillance_case", resource_id=row.pk)
                return Response(body)
        except IdempotencyConflict: return error_response(request, "IDEMPOTENCY_CONFLICT", 409)
        except ValueError as exc: return error_response(request, str(exc), 409 if str(exc) in {"VERSION_CONFLICT", "INVALID_CASE_TRANSITION"} else 403)


class AssignCase(CaseAction): action = "assign"
class EscalateCase(CaseAction): action = "escalate"
class ResolveCase(CaseAction): action = "resolve"


class RestrictionList(views.APIView):
    permission_classes = (SurveillanceViewer,)
    def get(self, request):
        rows = TradingRestriction.objects.filter(tenant_ref="default").order_by("-created_at")[:200]
        return Response({"results": RestrictionSerializer(rows, many=True).data})
    @extend_schema(parameters=COMMAND_PARAMETERS)
    def post(self, request):
        if not SurveillanceManager().has_permission(request, self): return error_response(request, "PERMISSION_DENIED", 403)
        required = ("scope_type", "scope_ref", "restriction_type", "reason")
        key, request_id, _ = _command_headers(request)
        if any(not request.data.get(field) for field in required) or not key: return error_response(request, "VALIDATION_ERROR", 422, {"required": [*required, "Idempotency-Key", "X-Request-ID"]})
        reason = str(request.data["reason"]).strip()
        try:
            row = TradingRestriction(tenant_ref="default", scope_type=request.data["scope_type"], scope_ref=str(request.data["scope_ref"]), restriction_type=request.data["restriction_type"], reason_code="INTERNAL_REVIEW", effective_from=timezone.now(), effective_to=request.data.get("effective_to"), created_by=str(request.user.pk), status="PENDING")
            row.full_clean()
        except Exception: return error_response(request, "VALIDATION_ERROR", 400)
        try:
            with transaction.atomic():
                record, fresh = begin_idempotent_request(key=key, tenant_ref="default", actor_ref=request.user.pk, endpoint="/api/v1/operator/surveillance/restrictions", method="POST", request_data={"scope_type": row.scope_type, "scope_ref": row.scope_ref, "restriction_type": row.restriction_type, "effective_to": str(row.effective_to or ""), "reason": reason})
                if not fresh and record.response_body is not None: return Response(record.response_body, status=record.response_status)
                row.save(); audit(tenant_ref="default", actor_ref=request.user.pk, action="surveillance.restriction.requested", resource_type="trading_restriction", resource_ref=row.id, reason=reason)
                body = RestrictionSerializer(row).data
                _application_audit(request, request_id=request_id, action="surveillance.restriction.requested", resource_type="trading_restriction", resource_id=row.pk, reason=reason, context={"status": row.status})
                complete_idempotent_request(record, status=201, body=body, resource_type="trading_restriction", resource_id=row.pk)
                return Response(body, status=status.HTTP_201_CREATED)
        except IdempotencyConflict: return error_response(request, "IDEMPOTENCY_CONFLICT", 409)


class ApproveRestriction(views.APIView):
    permission_classes = (SurveillanceManager,)
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    def post(self, request, restriction_id):
        row = TradingRestriction.objects.filter(id=restriction_id, tenant_ref="default").first()
        if not row: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        if row.created_by == str(request.user.pk): return error_response(request, "SELF_APPROVAL_FORBIDDEN", 403)
        key, request_id, expected_version = _command_headers(request, versioned=True); reason = str(request.data.get("reason", "")).strip()
        if not key or not reason: return error_response(request, "VALIDATION_ERROR", 422, {"required": ["Idempotency-Key", "X-Request-ID", "If-Match", "reason"]})
        try:
            with transaction.atomic():
                row = TradingRestriction.objects.select_for_update().get(pk=row.pk)
                record, fresh = begin_idempotent_request(key=key, tenant_ref=row.tenant_ref, actor_ref=request.user.pk, endpoint=f"/api/v1/operator/surveillance/restrictions/{row.pk}/approve", method="POST", request_data={"restriction_id": str(row.pk), "reason": reason, "expected_version": expected_version})
                if not fresh and record.response_body is not None: return Response(record.response_body, status=record.response_status)
                if row.updated_at.isoformat() != expected_version: raise ValueError("VERSION_CONFLICT")
                if row.status != "PENDING": raise ValueError("INVALID_RESTRICTION_TRANSITION")
                row.approved_by = str(request.user.pk); row.status = "ACTIVE"; row.full_clean(); row.save()
                audit(tenant_ref=row.tenant_ref, actor_ref=request.user.pk, action="surveillance.restriction.approved", resource_type="trading_restriction", resource_ref=row.id, reason=reason)
                enqueue_event(aggregate_type="trading_restriction", aggregate_id=row.id, event_type="regulatory.surveillance.restriction.applied.v1", payload={"restriction_id": str(row.id), "scope_type": row.scope_type, "scope_ref": row.scope_ref}, tenant_ref=row.tenant_ref)
                body = RestrictionSerializer(row).data
                _application_audit(request, request_id=request_id, action="surveillance.restriction.approved", resource_type="trading_restriction", resource_id=row.pk, reason=reason, context={"status": row.status})
                complete_idempotent_request(record, status=200, body=body, resource_type="trading_restriction", resource_id=row.pk)
                return Response(body)
        except IdempotencyConflict: return error_response(request, "IDEMPOTENCY_CONFLICT", 409)
        except ValueError as exc: return error_response(request, str(exc), 409)


class RemoveRestriction(views.APIView):
    permission_classes = (SurveillanceManager,)
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    def post(self, request, restriction_id):
        row = TradingRestriction.objects.filter(id=restriction_id, tenant_ref="default").first()
        if not row: return error_response(request, "RESOURCE_NOT_FOUND", 404)
        if row.approved_by == str(request.user.pk): return error_response(request, "SELF_APPROVAL_FORBIDDEN", 403)
        reason = str(request.data.get("reason", "")).strip(); key, request_id, expected_version = _command_headers(request, versioned=True)
        if not reason or not key: return error_response(request, "VALIDATION_ERROR", 422, {"required": ["Idempotency-Key", "X-Request-ID", "If-Match", "reason"]})
        try:
            with transaction.atomic():
                row = TradingRestriction.objects.select_for_update().get(pk=row.pk)
                record, fresh = begin_idempotent_request(key=key, tenant_ref=row.tenant_ref, actor_ref=request.user.pk, endpoint=f"/api/v1/operator/surveillance/restrictions/{row.pk}/remove", method="POST", request_data={"restriction_id": str(row.pk), "reason": reason, "expected_version": expected_version})
                if not fresh and record.response_body is not None: return Response(record.response_body, status=record.response_status)
                if row.updated_at.isoformat() != expected_version: raise ValueError("VERSION_CONFLICT")
                if row.status != "ACTIVE": raise ValueError("INVALID_RESTRICTION_TRANSITION")
                row.status = "REMOVED"; row.effective_to = timezone.now(); row.save()
                audit(tenant_ref=row.tenant_ref, actor_ref=request.user.pk, action="surveillance.restriction.removed", resource_type="trading_restriction", resource_ref=row.id, reason=reason)
                enqueue_event(aggregate_type="trading_restriction", aggregate_id=row.id, event_type="regulatory.surveillance.restriction.removed.v1", payload={"restriction_id": str(row.id)}, tenant_ref=row.tenant_ref)
                body = RestrictionSerializer(row).data
                _application_audit(request, request_id=request_id, action="surveillance.restriction.removed", resource_type="trading_restriction", resource_id=row.pk, reason=reason, context={"status": row.status})
                complete_idempotent_request(record, status=200, body=body, resource_type="trading_restriction", resource_id=row.pk)
                return Response(body)
        except IdempotencyConflict: return error_response(request, "IDEMPOTENCY_CONFLICT", 409)
        except ValueError as exc: return error_response(request, str(exc), 409)


class RuleList(views.APIView):
    permission_classes = (SurveillanceViewer,)
    def get(self, request): return Response({"results": RuleSerializer(SurveillanceRule.objects.order_by("name", "-version"), many=True).data})
