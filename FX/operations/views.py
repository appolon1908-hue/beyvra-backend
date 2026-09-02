from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import IdempotencyConflict, begin_idempotent_request, complete_idempotent_request

from .artifacts import open_private_artifact

from .models import (
    AccountDeletionRequest,
    AccountFreeze,
    AccountSession,
    AuditEvent,
    FraudCase,
    LegalHold,
    Notification,
    NotificationPreference,
    OperatorActionRequest,
    OperatorRole,
    PrivacyExportJob,
    ReconciliationCheck,
    ReportJob,
    Statement,
    SupportCase,
    SupportCaseEvent,
    SecurityEvent,
    TradeConfirmation,
    TradingHalt,
    TransactionHistoryEntry,
)
from .metrics import (
    privacy_exports_created,
    report_jobs_created,
    support_case_age,
    support_escalations,
    support_first_response,
    support_resolution,
    unauthorized_operator_attempts,
)
from .permissions import (
    IsAnyOperator,
    IsComplianceOperator,
    IsComplianceManager,
    IsFinancialOperator,
    IsFinancialManager,
    IsManagerOperator,
    IsOperationsManager,
    IsSecurityAnalyst,
    IsSecurityManager,
    IsSupportAgent,
    IsSupportOperator,
)
from .serializers import (
    AccountDeletionSerializer,
    CustomerSupportEventSerializer,
    FraudCaseSerializer,
    NotificationSerializer,
    PreferenceSerializer,
    PrivacyExportSerializer,
    ReportJobSerializer,
    StatementSerializer,
    SupportCaseSerializer,
    SupportMessageSerializer,
    TransactionSerializer,
    TransactionQuerySerializer,
    TradeConfirmationSerializer,
)
from .services import (
    ACTION_ROLE_POLICY,
    REAL_FEATURE_FLAGS,
    approve_operator_request,
    deletion_disposition,
    execute_operator_request,
    issue_simulation_statement,
    reconcile_operational_domains,
    revoke_bound_session,
    stable_hash,
    tenant_account_q,
    tenant_for,
)


COMMAND_PARAMETERS = [
    OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Request-ID", str, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Correlation-ID", str, OpenApiParameter.HEADER, required=False),
]
VERSIONED_COMMAND_PARAMETERS = [*COMMAND_PARAMETERS, OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)]


class TenantMixin:
    def tenant_id(self):
        return tenant_for(self.request.user)


def _command_context(request, *, require_version=False):
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


def _begin_command(request, *, tenant, key, payload):
    return begin_idempotent_request(
        key=key, tenant_ref=tenant, actor_ref=request.user.pk, endpoint=request.path,
        method=request.method, request_data={"api_version": "v1", **payload},
    )


def _replay(record):
    if record.response_status is None or record.response_body is None:
        return Response({"code": "COMMAND_IN_PROGRESS", "message": "Command result is not yet available."}, status=409)
    return Response(record.response_body, status=record.response_status)


def _application_audit(request, *, action, resource_type, resource_id, request_id, correlation_id, reason, context=None):
    ApplicationAuditEvent.objects.create(
        actor_ref=str(request.user.pk), action=action, resource_type=resource_type, resource_id=str(resource_id),
        request_id=request_id, correlation_id=correlation_id, context=context or {}, reason=reason[:255], occurred_at=timezone.now(),
    )


class SupportCaseListCreate(TenantMixin, generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = SupportCaseSerializer

    def get_queryset(self):
        return SupportCase.objects.filter(
            tenant_id=self.tenant_id(), account=self.request.user
        ).order_by("-created_at")

    @transaction.atomic
    def perform_create(self, serializer):
        case = serializer.save(tenant_id=self.tenant_id(), account=self.request.user)
        SupportCaseEvent.objects.create(
            tenant_id=self.tenant_id(),
            account=self.request.user,
            case=case,
            event_type="CASE_CREATED",
            visibility="CUSTOMER_VISIBLE_MESSAGE",
            actor=self.request.user,
        )
        AuditEvent.objects.create(
            tenant_id=self.tenant_id(),
            actor=self.request.user,
            action="SUPPORT_CASE_CREATED",
            target=str(case.pk),
        )


class SupportCaseDetail(TenantMixin, generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = SupportCaseSerializer
    lookup_url_kwarg = "case_id"
    lookup_field = "case_id"

    def get_queryset(self):
        return SupportCase.objects.filter(
            tenant_id=self.tenant_id(), account=self.request.user
        )

    def retrieve(self, request, *args, **kwargs):
        case = self.get_object()
        data = self.get_serializer(case).data
        events = case.timeline.filter(visibility="CUSTOMER_VISIBLE_MESSAGE").order_by(
            "created_at"
        )
        data["timeline"] = CustomerSupportEventSerializer(events, many=True).data
        return Response(data)


class SupportMessageCreate(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, case_id):
        serializer = SupportMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = get_object_or_404(
            SupportCase,
            case_id=case_id,
            tenant_id=self.tenant_id(),
            account=request.user,
        )
        event = SupportCaseEvent.objects.create(
            tenant_id=self.tenant_id(),
            account=request.user,
            case=case,
            event_type="CUSTOMER_RESPONSE",
            visibility="CUSTOMER_VISIBLE_MESSAGE",
            body_safe=serializer.validated_data["message"],
            actor=request.user,
        )
        return Response(
            CustomerSupportEventSerializer(event).data, status=status.HTTP_201_CREATED
        )


class TransactionList(TenantMixin, generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = TransactionSerializer
    history_type = None

    def get_queryset(self):
        query = TransactionQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        qs = TransactionHistoryEntry.objects.filter(
            tenant_id=self.tenant_id(), account=self.request.user
        )
        if self.history_type:
            qs = qs.filter(type=self.history_type)
        if query.validated_data.get("date_from"):
            qs = qs.filter(occurred_at__gte=query.validated_data["date_from"])
        if query.validated_data.get("date_to"):
            qs = qs.filter(occurred_at__lte=query.validated_data["date_to"])
        return qs


class TradeConfirmationList(TenantMixin, generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = TradeConfirmationSerializer

    def get_queryset(self):
        query = TransactionQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        rows = TradeConfirmation.objects.filter(
            tenant_id=self.tenant_id(), account=self.request.user
        )
        if query.validated_data.get("date_from"):
            rows = rows.filter(executed_at__gte=query.validated_data["date_from"])
        if query.validated_data.get("date_to"):
            rows = rows.filter(executed_at__lte=query.validated_data["date_to"])
        return rows


class NotificationList(TenantMixin, generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(
            tenant_id=self.tenant_id(), account=self.request.user
        ).order_by("-created_at")


class NotificationRead(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, notification_id):
        updated = Notification.objects.filter(
            notification_id=notification_id,
            tenant_id=self.tenant_id(),
            account=request.user,
        ).update(read_at=timezone.now(), status="READ")
        if not updated:
            raise NotFound("Resource not found")
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationReadAll(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        Notification.objects.filter(
            tenant_id=self.tenant_id(), account=request.user, read_at__isnull=True
        ).update(read_at=timezone.now(), status="READ")
        return Response(status=status.HTTP_204_NO_CONTENT)


class PreferenceList(TenantMixin, generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PreferenceSerializer

    def get_queryset(self):
        return NotificationPreference.objects.filter(
            tenant_id=self.tenant_id(), account=self.request.user
        )

    def perform_create(self, serializer):
        category = serializer.validated_data["category"]
        if category in {"SECURITY", "FINANCIAL"} and not serializer.validated_data.get(
            "enabled", True
        ):
            serializer.validated_data["enabled"] = True
        serializer.save(tenant_id=self.tenant_id(), account=self.request.user)

    def patch(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.validated_data["category"]
        enabled = serializer.validated_data.get("enabled", True)
        if category in {"SECURITY", "FINANCIAL"} and not enabled:
            return Response(
                {
                    "code": "MANDATORY_NOTIFICATION",
                    "message": "This notification is required for account safety.",
                },
                status=400,
            )
        preference, _ = NotificationPreference.objects.update_or_create(
            tenant_id=self.tenant_id(),
            account=request.user,
            category=category,
            channel=serializer.validated_data["channel"],
            defaults={"enabled": enabled},
        )
        return Response(self.get_serializer(preference).data)


class ReportJobListCreate(TenantMixin, generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ReportJobSerializer

    def get_queryset(self):
        return ReportJob.objects.filter(
            tenant_id=self.tenant_id(), account=self.request.user
        ).order_by("-created_at")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        report_type = request.data.get("report_type", "ACTIVITY")
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {
                    "code": "IDEMPOTENCY_KEY_REQUIRED",
                    "message": "An idempotency key is required.",
                },
                status=400,
            )
        if len(idempotency_key) > 128:
            raise ValidationError("Invalid idempotency key")
        if report_type not in {"ACTIVITY", "TRANSACTIONS", "TRADE", "FEE"}:
            raise ValidationError("Invalid report type")
        reconciliation = reconcile_operational_domains(tenant_id=self.tenant_id())
        job, created = ReportJob.objects.get_or_create(
            tenant_id=self.tenant_id(),
            account=request.user,
            idempotency_key=idempotency_key,
            defaults={
                "report_type": report_type,
                "parameters_hash": stable_hash(request.data),
                "reconciliation_passed": all(
                    check.status == "PASS" for check in reconciliation
                ),
            },
        )
        if created:
            from .tasks import generate_report_artifact

            report_jobs_created.labels(report_type=job.report_type).inc()
            transaction.on_commit(lambda: generate_report_artifact.delay(str(job.pk)))
        return Response(self.get_serializer(job).data, status=201 if created else 200)


class ReportJobDownload(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, job_id):
        job = get_object_or_404(
            ReportJob,
            job_id=job_id,
            tenant_id=self.tenant_id(),
            account=request.user,
            status="COMPLETED",
            reconciliation_passed=True,
            expires_at__gt=timezone.now(),
        )
        try:
            artifact = open_private_artifact(job.artifact_ref)
        except (FileNotFoundError, OSError):
            raise NotFound("Resource not found")
        AuditEvent.objects.create(
            tenant_id=self.tenant_id(),
            actor=request.user,
            action="REPORT_DOWNLOADED",
            target=str(job.pk),
        )
        return FileResponse(
            artifact,
            as_attachment=True,
            filename=f"beyvra-report-{job.pk}.csv",
            content_type="text/csv; charset=utf-8",
        )


class StatementList(TenantMixin, generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = StatementSerializer

    def get_queryset(self):
        return Statement.objects.filter(
            tenant_id=self.tenant_id(),
            account=self.request.user,
            reconciliation_passed=True,
        ).order_by("-period_end", "-version")


class PrivacyExportListCreate(TenantMixin, generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PrivacyExportSerializer

    def get_queryset(self):
        return PrivacyExportJob.objects.filter(
            tenant_id=self.tenant_id(), account=self.request.user
        ).order_by("-created_at")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            return Response(
                {
                    "code": "IDEMPOTENCY_KEY_REQUIRED",
                    "message": "An idempotency key is required.",
                },
                status=400,
            )
        if len(key) > 128:
            raise ValidationError("Invalid idempotency key")
        job, created = PrivacyExportJob.objects.get_or_create(
            tenant_id=self.tenant_id(),
            account=request.user,
            idempotency_key=key,
            defaults={"policy_version": "PRIVACY-EXPORT-SCHEMA-v1"},
        )
        if created:
            from .tasks import generate_privacy_export

            privacy_exports_created.inc()
            transaction.on_commit(lambda: generate_privacy_export.delay(str(job.pk)))
        return Response(self.get_serializer(job).data, status=201 if created else 200)


class PrivacyExportDownload(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, job_id):
        job = get_object_or_404(
            PrivacyExportJob,
            job_id=job_id,
            tenant_id=self.tenant_id(),
            account=request.user,
            status="COMPLETED",
            expires_at__gt=timezone.now(),
        )
        try:
            artifact = open_private_artifact(job.artifact_ref)
        except (FileNotFoundError, OSError):
            raise NotFound("Resource not found")
        AuditEvent.objects.create(
            tenant_id=self.tenant_id(),
            actor=request.user,
            action="PRIVACY_EXPORT_DOWNLOADED",
            target=str(job.pk),
        )
        return FileResponse(
            artifact,
            as_attachment=True,
            filename=f"beyvra-privacy-export-{job.pk}.json",
            content_type="application/json",
        )


class AccountDeletionListCreate(TenantMixin, generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = AccountDeletionSerializer

    def get_queryset(self):
        return AccountDeletionRequest.objects.filter(
            tenant_id=self.tenant_id(), account=self.request.user
        ).order_by("-requested_at")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            return Response(
                {
                    "code": "IDEMPOTENCY_KEY_REQUIRED",
                    "message": "An idempotency key is required.",
                },
                status=400,
            )
        disposition = deletion_disposition(
            tenant_id=self.tenant_id(), account=request.user
        )
        deletion, created = AccountDeletionRequest.objects.get_or_create(
            tenant_id=self.tenant_id(),
            account=request.user,
            idempotency_key=key,
            defaults=disposition,
        )
        AuditEvent.objects.get_or_create(
            tenant_id=self.tenant_id(),
            actor=request.user,
            action="ACCOUNT_DELETION_REQUESTED",
            target=str(deletion.pk),
        )
        return Response(
            self.get_serializer(deletion).data, status=201 if created else 200
        )


class SessionList(TenantMixin, generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = None

    def get(self, request):
        rows = AccountSession.objects.filter(
            tenant_id=self.tenant_id(),
            account=request.user,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).values(
            "session_id",
            "created_at",
            "last_seen_at",
            "expires_at",
            "auth_strength",
            "mfa_verified_at",
        )
        return Response(list(rows))


class SessionRevoke(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, session_id):
        if not revoke_bound_session(user=request.user, session_id=session_id):
            raise NotFound("Resource not found")
        AuditEvent.objects.create(
            tenant_id=self.tenant_id(),
            actor=request.user,
            action="SESSION_REVOKED",
            target=str(session_id),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionRevokeOthers(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        current = request.data.get("current_session_id")
        if not current:
            return Response(
                {
                    "code": "CURRENT_SESSION_REQUIRED",
                    "message": "The current session is required.",
                },
                status=400,
            )
        count = (
            AccountSession.objects.filter(
                tenant_id=self.tenant_id(),
                account=request.user,
                revoked_at__isnull=True,
            )
            .exclude(session_id=current)
            .update(revoked_at=timezone.now())
        )
        AuditEvent.objects.create(
            tenant_id=self.tenant_id(),
            actor=request.user,
            action="OTHER_SESSIONS_REVOKED",
            target="account",
            metadata_safe={"count": count},
        )
        return Response({"revoked": count})


class SafetyFlags(APIView):
    permission_classes = (IsSupportOperator,)

    def get(self, request):
        return Response(REAL_FEATURE_FLAGS)


class OperatorFreeze(APIView):
    permission_classes = (IsSecurityManager,)

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request, account_id):
        tenant = request.headers.get(
            "X-Beyvra-Tenant", tenant_for(request.user)
        ).lower()
        command, error = _command_context(request)
        if error:
            return error
        key, request_id, correlation_id, _ = command
        account = get_object_or_404(
            get_user_model().objects.filter(tenant_account_q(tenant)), pk=account_id
        )
        level = request.data.get("level", "FULL")
        if level not in {"PARTIAL", "FULL"}:
            return Response(
                {
                    "code": "INVALID_FREEZE_LEVEL",
                    "message": "The requested action is invalid.",
                },
                status=400,
            )
        reason_code = request.data.get("reason_code", "ACCOUNT_REVIEW_REQUIRED")
        try:
            record, created = _begin_command(request, tenant=tenant, key=key, payload={"account_id": account_id, "level": level, "reason_code": reason_code})
        except IdempotencyConflict:
            return Response({"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}, status=409)
        if not created:
            return _replay(record)
        freeze, _ = AccountFreeze.objects.update_or_create(
            tenant_id=tenant,
            account=account,
            released_at__isnull=True,
            defaults={
                "level": level,
                "reason_code": reason_code,
                "actor": request.user,
            },
        )
        AuditEvent.objects.create(
            tenant_id=tenant,
            actor=request.user,
            role="security_manager",
            action="ACCOUNT_FROZEN",
            target=str(account_id),
            reason=freeze.reason_code,
        )
        body = {"level": freeze.level, "freeze_id": freeze.pk}
        _application_audit(request, action="operations.account.frozen", resource_type="account_freeze", resource_id=freeze.pk, request_id=request_id, correlation_id=correlation_id, reason=freeze.reason_code, context={"tenant_id": tenant, "account_id": str(account_id), "level": freeze.level})
        complete_idempotent_request(record, status=201, body=body, resource_type="account_freeze", resource_id=freeze.pk)
        return Response(body, status=201)


class OperatorApprove(APIView):
    permission_classes = (IsManagerOperator,)

    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request, request_id):
        tenant = request.headers.get(
            "X-Beyvra-Tenant", tenant_for(request.user)
        ).lower()
        command, error = _command_context(request, require_version=True)
        if error:
            return error
        key, command_request_id, correlation_id, expected_version = command
        try:
            record, created = _begin_command(request, tenant=tenant, key=key, payload={"operator_request_id": str(request_id), "action": "APPROVE", "expected_version": expected_version})
        except IdempotencyConflict:
            return Response({"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}, status=409)
        if not created:
            return _replay(record)
        current = OperatorActionRequest.objects.filter(pk=request_id, tenant_id=tenant).values_list("status", flat=True).first()
        if current is None:
            record.delete()
            return Response({"code": "ACTION_NOT_ALLOWED", "message": "The requested action is not available."}, status=403)
        if current != expected_version:
            record.delete()
            return Response({"code": "VERSION_CONFLICT", "message": "Operator request version does not match."}, status=409)
        roles = set(
            OperatorRole.objects.filter(
                user=request.user, tenant_id=tenant
            ).values_list("role", flat=True)
        )
        try:
            action = approve_operator_request(
                request_id=request_id,
                tenant_id=tenant,
                approver=request.user,
                approver_roles=roles,
            )
        except (PermissionError, OperatorActionRequest.DoesNotExist) as exc:
            record.delete()
            action = (
                "self_approval"
                if "SELF_APPROVAL_FORBIDDEN" in str(exc)
                else "approval_denied"
            )
            unauthorized_operator_attempts.labels(action=action).inc()
            return Response(
                {
                    "code": "ACTION_NOT_ALLOWED",
                    "message": "The requested action is not available.",
                },
                status=403,
            )
        body = {"request_id": str(action.request_id), "status": "APPROVED", "version": "APPROVED"}
        _application_audit(request, action="operations.action.approved", resource_type="operator_action", resource_id=action.pk, request_id=command_request_id, correlation_id=correlation_id, reason=action.reason, context={"tenant_id": tenant})
        complete_idempotent_request(record, status=200, body=body, resource_type="operator_action", resource_id=action.pk)
        return Response(body)


class OperatorExecute(APIView):
    permission_classes = (IsManagerOperator,)

    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request, request_id):
        tenant = operator_tenant(request)
        command, error = _command_context(request, require_version=True)
        if error:
            return error
        key, command_request_id, correlation_id, expected_version = command
        try:
            record, created = _begin_command(request, tenant=tenant, key=key, payload={"operator_request_id": str(request_id), "action": "EXECUTE", "expected_version": expected_version})
        except IdempotencyConflict:
            return Response({"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}, status=409)
        if not created:
            return _replay(record)
        current = OperatorActionRequest.objects.filter(pk=request_id, tenant_id=tenant).values_list("status", flat=True).first()
        if current is None:
            record.delete()
            return Response({"code": "ACTION_NOT_ALLOWED", "message": "The requested action is not available."}, status=403)
        if current != expected_version:
            record.delete()
            return Response({"code": "VERSION_CONFLICT", "message": "Operator request version does not match."}, status=409)
        roles = set(
            OperatorRole.objects.filter(
                user=request.user, tenant_id=tenant
            ).values_list("role", flat=True)
        )
        try:
            action = execute_operator_request(
                request_id=request_id,
                tenant_id=tenant,
                executor=request.user,
                executor_roles=roles,
            )
        except (PermissionError, OperatorActionRequest.DoesNotExist):
            record.delete()
            return Response(
                {
                    "code": "ACTION_NOT_ALLOWED",
                    "message": "The requested action is not available.",
                },
                status=403,
            )
        body = {"request_id": str(action.request_id), "status": "EXECUTED", "version": "EXECUTED"}
        _application_audit(request, action="operations.action.executed", resource_type="operator_action", resource_id=action.pk, request_id=command_request_id, correlation_id=correlation_id, reason=action.reason, context={"tenant_id": tenant, "action_type": action.action_type})
        complete_idempotent_request(record, status=200, body=body, resource_type="operator_action", resource_id=action.pk)
        return Response(body)


def operator_tenant(request):
    return request.headers.get("X-Beyvra-Tenant", tenant_for(request.user)).lower()


def operator_roles(request):
    return set(
        OperatorRole.objects.filter(
            user=request.user, tenant_id=operator_tenant(request)
        ).values_list("role", flat=True)
    )


class OperatorFraudCases(generics.ListCreateAPIView):
    permission_classes = (IsSecurityAnalyst,)
    serializer_class = FraudCaseSerializer

    def get_queryset(self):
        return FraudCase.objects.filter(
            tenant_id=operator_tenant(self.request)
        ).order_by("-created_at")

    def perform_create(self, serializer):
        if tenant_for(serializer.validated_data["account"]) != operator_tenant(
            self.request
        ):
            raise ValidationError({"account": "Resource not found."})
        case = serializer.save(tenant_id=operator_tenant(self.request))
        AuditEvent.objects.create(
            tenant_id=case.tenant_id,
            actor=self.request.user,
            role="security_analyst",
            action="FRAUD_CASE_CREATED",
            target=str(case.pk),
        )


class OperatorFraudCaseUpdate(APIView):
    permission_classes = (IsSecurityAnalyst,)

    @transaction.atomic
    def post(self, request, case_id):
        case = get_object_or_404(
            FraudCase, case_id=case_id, tenant_id=operator_tenant(request)
        )
        next_status = request.data.get("status")
        if next_status not in dict(FraudCase.STATUSES):
            return Response(
                {
                    "code": "INVALID_CASE_STATUS",
                    "message": "The requested action is invalid.",
                },
                status=400,
            )
        case.status = next_status
        if next_status in {"RESOLVED", "CLOSED"}:
            case.resolved_at = timezone.now()
            case.resolution = request.data.get("resolution", "")[:2000]
        case.save(update_fields=("status", "resolved_at", "resolution", "updated_at"))
        AuditEvent.objects.create(
            tenant_id=case.tenant_id,
            actor=request.user,
            action="FRAUD_CASE_STATUS_CHANGED",
            target=str(case.pk),
            reason=next_status,
        )
        return Response(FraudCaseSerializer(case).data)


class OperatorSupportCases(generics.ListAPIView):
    permission_classes = (IsSupportOperator,)
    serializer_class = SupportCaseSerializer

    def get_queryset(self):
        return SupportCase.objects.filter(
            tenant_id=operator_tenant(self.request)
        ).order_by("-created_at")


class OperatorSupportEvent(APIView):
    permission_classes = (IsSupportAgent,)

    @transaction.atomic
    def post(self, request, case_id):
        case = get_object_or_404(
            SupportCase, case_id=case_id, tenant_id=operator_tenant(request)
        )
        event_type = request.data.get("event_type")
        allowed = {
            "MESSAGE_ADDED",
            "INTERNAL_NOTE",
            "ASSIGNED",
            "STATUS_CHANGED",
            "ESCALATED",
            "RESOLVED",
            "REOPENED",
        }
        if event_type not in allowed:
            return Response(
                {
                    "code": "INVALID_CASE_ACTION",
                    "message": "The requested action is invalid.",
                },
                status=400,
            )
        if event_type == "ESCALATED":
            team = request.data.get("team")
            if team not in {
                "SECURITY",
                "COMPLIANCE",
                "FINANCIAL",
                "ENGINEERING",
                "OPERATIONS",
            }:
                return Response(
                    {
                        "code": "INVALID_ESCALATION",
                        "message": "The requested action is invalid.",
                    },
                    status=400,
                )
            case.status, case.assigned_team = "ESCALATED", team
            case.save(update_fields=("status", "assigned_team", "updated_at"))
            support_escalations.labels(destination=team).inc()
        elif event_type == "ASSIGNED":
            assigned_to = get_object_or_404(
                get_user_model().objects.filter(tenant_account_q(case.tenant_id)),
                pk=request.data.get("assigned_to"),
            )
            if not OperatorRole.objects.filter(
                user=assigned_to,
                tenant_id=case.tenant_id,
                role__in={"support_agent", "support_manager", "platform_admin"},
            ).exists():
                raise ValidationError("Invalid support assignee")
            case.assigned_to = assigned_to
            case.save(update_fields=("assigned_to", "updated_at"))
        elif event_type == "STATUS_CHANGED":
            next_status = request.data.get("status")
            if next_status not in dict(SupportCase.STATUSES):
                raise ValidationError("Invalid support status")
            case.status = next_status
            case.resolved_at = (
                timezone.now() if next_status in {"RESOLVED", "CLOSED"} else None
            )
            case.save(update_fields=("status", "resolved_at", "updated_at"))
        elif event_type == "RESOLVED":
            case.status = "RESOLVED"
            case.resolved_at = timezone.now()
            case.save(update_fields=("status", "resolved_at", "updated_at"))
        elif event_type == "REOPENED":
            case.status = "OPEN"
            case.resolved_at = None
            case.save(update_fields=("status", "resolved_at", "updated_at"))
        visibility = (
            "INTERNAL_NOTE"
            if event_type == "INTERNAL_NOTE"
            else "CUSTOMER_VISIBLE_MESSAGE"
        )
        event = SupportCaseEvent.objects.create(
            tenant_id=case.tenant_id,
            account=case.account,
            case=case,
            event_type=event_type,
            visibility=visibility,
            body_safe=request.data.get("message", "")[:5000],
            actor=request.user,
        )
        age_seconds = (timezone.now() - case.created_at).total_seconds()
        support_case_age.observe(age_seconds)
        if visibility == "CUSTOMER_VISIBLE_MESSAGE" and not case.timeline.filter(
            visibility="CUSTOMER_VISIBLE_MESSAGE",
            actor__is_staff=True,
        ).exclude(pk=event.pk).exists():
            support_first_response.observe(age_seconds)
        if case.status in {"RESOLVED", "CLOSED"}:
            support_resolution.observe(age_seconds)
        AuditEvent.objects.create(
            tenant_id=case.tenant_id,
            actor=request.user,
            action="SUPPORT_CASE_" + event_type,
            target=str(case.pk),
            reason=request.data.get("reason", "")[:500],
        )
        return Response(CustomerSupportEventSerializer(event).data, status=201)


class OperatorActionCreate(APIView):
    permission_classes = (IsManagerOperator,)

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        action_type = request.data.get("action_type")
        if action_type not in {
            "UNFREEZE",
            "COMPLIANCE_OVERRIDE",
            "FINANCIAL_OVERRIDE",
            "WITHDRAWAL_OVERRIDE",
            "PROVIDER_ACTIVATION",
            "REAL_MONEY_ACTIVATION",
            "KILL_SWITCH_RELEASE",
            "LEGAL_HOLD_RELEASE",
        }:
            return Response(
                {
                    "code": "INVALID_ACTION_TYPE",
                    "message": "The requested action is invalid.",
                },
                status=400,
            )
        tenant = operator_tenant(request)
        command, error = _command_context(request)
        if error:
            return error
        key, command_request_id, correlation_id, _ = command
        requester_roles = set(
            OperatorRole.objects.filter(user=request.user, tenant_id=tenant).values_list(
                "role", flat=True
            )
        )
        if not requester_roles & ACTION_ROLE_POLICY[action_type]:
            unauthorized_operator_attempts.labels(action="request_denied").inc()
            return Response(
                {
                    "code": "ACTION_NOT_ALLOWED",
                    "message": "The requested action is not available.",
                },
                status=403,
            )
        reason = request.data.get("reason", "").strip()
        if not reason:
            return Response(
                {"code": "REASON_REQUIRED", "message": "A reason is required."},
                status=400,
            )
        target_ref = request.data.get("target_ref", "")[:128]
        try:
            record, created = _begin_command(request, tenant=tenant, key=key, payload={"action_type": action_type, "target_ref": target_ref, "reason": reason})
        except IdempotencyConflict:
            return Response({"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}, status=409)
        if not created:
            return _replay(record)
        action = OperatorActionRequest.objects.create(
            tenant_id=tenant,
            action_type=action_type,
            target_ref=target_ref,
            requested_by=request.user,
            reason=reason[:500],
            expires_at=timezone.now() + timedelta(hours=1),
        )
        AuditEvent.objects.create(
            tenant_id=action.tenant_id,
            actor=request.user,
            action="OPERATOR_ACTION_REQUESTED",
            target=action.target_ref,
            reason=action.reason,
            request_id=action.pk,
        )
        body = {"request_id": str(action.pk), "status": action.status, "version": action.status}
        _application_audit(request, action="operations.action.requested", resource_type="operator_action", resource_id=action.pk, request_id=command_request_id, correlation_id=correlation_id, reason=action.reason, context={"tenant_id": tenant, "action_type": action.action_type, "target_ref": action.target_ref})
        complete_idempotent_request(record, status=201, body=body, resource_type="operator_action", resource_id=action.pk)
        return Response(body, status=201)


class OperatorLegalHold(APIView):
    permission_classes = (IsComplianceManager,)

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request, account_id):
        tenant = operator_tenant(request)
        command, error = _command_context(request)
        if error:
            return error
        key, request_id, correlation_id, _ = command
        account = get_object_or_404(
            get_user_model().objects.filter(tenant_account_q(tenant)), pk=account_id
        )
        reason = request.data.get("reason", "policy hold")[:500]
        try:
            record, created = _begin_command(request, tenant=tenant, key=key, payload={"account_id": account_id, "reason": reason})
        except IdempotencyConflict:
            return Response({"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}, status=409)
        if not created:
            return _replay(record)
        hold = LegalHold.objects.create(
            tenant_id=tenant,
            account=account,
            reason=reason,
            created_by=request.user,
        )
        AuditEvent.objects.create(
            tenant_id=hold.tenant_id,
            actor=request.user,
            action="LEGAL_HOLD_CREATED",
            target=str(hold.pk),
            reason=hold.reason,
        )
        body = {"hold_id": hold.pk, "active": True}
        _application_audit(request, action="operations.legal_hold.created", resource_type="legal_hold", resource_id=hold.pk, request_id=request_id, correlation_id=correlation_id, reason=hold.reason, context={"tenant_id": tenant, "account_id": str(account_id)})
        complete_idempotent_request(record, status=201, body=body, resource_type="legal_hold", resource_id=hold.pk)
        return Response(body, status=201)


class OperatorAccountSummary(APIView):
    permission_classes = (IsAnyOperator,)

    def get(self, request, account_id):
        tenant = operator_tenant(request)
        account = get_object_or_404(
            get_user_model().objects.filter(tenant_account_q(tenant)), pk=account_id
        )
        active_freeze = AccountFreeze.objects.filter(
            tenant_id=tenant, account=account, released_at__isnull=True
        ).values("level", "reason_code", "created_at").first()
        recent_security = list(
            SecurityEvent.objects.filter(tenant_id=tenant, account=account)
            .order_by("-occurred_at")
            .values("event_type", "risk_level", "occurred_at", "resolved")[:10]
        )
        history_counts = list(
            TransactionHistoryEntry.objects.filter(
                tenant_id=tenant, account=account, simulation=True
            )
            .values("type")
            .annotate(count=Count("entry_id"))
            .order_by("type")
        )
        AuditEvent.objects.create(
            tenant_id=tenant,
            actor=request.user,
            role=sorted(operator_roles(request))[0],
            action="OPERATOR_ACCOUNT_SUMMARY_VIEWED",
            target=f"account:{account.pk}",
        )
        return Response(
            {
                "account_ref": str(account.pk),
                "account_state": "ACTIVE" if account.is_active else "DISABLED",
                "verification_summary": {
                    "status": getattr(account, "verification_status", "UNKNOWN"),
                    "email_verified": bool(getattr(account, "email_verified", False)),
                    "phone_verified": bool(getattr(account, "phone_verified", False)),
                },
                "active_restriction": active_freeze,
                "recent_security_events": recent_security,
                "simulation_history_counts": history_counts,
                "wallet_feature_state": REAL_FEATURE_FLAGS,
                "open_support_cases": SupportCase.objects.filter(
                    tenant_id=tenant,
                    account=account,
                    status__in={"OPEN", "PENDING_CUSTOMER", "PENDING_INTERNAL", "ESCALATED"},
                ).count(),
            }
        )


class OperatorComplianceState(APIView):
    permission_classes = (IsComplianceOperator,)

    def get(self, request, account_id):
        tenant = operator_tenant(request)
        account = get_object_or_404(
            get_user_model().objects.filter(tenant_account_q(tenant)), pk=account_id
        )
        return Response(
            {
                "account_ref": str(account.pk),
                "verification_status": getattr(account, "verification_status", "UNKNOWN"),
                "document_verification": getattr(account, "document_verification", "UNKNOWN"),
                "face_verification": getattr(account, "face_verification", "UNKNOWN"),
                "active_legal_hold": LegalHold.objects.filter(
                    tenant_id=tenant, account=account, active=True
                ).exists(),
            }
        )


class OperatorFinancialState(APIView):
    permission_classes = (IsFinancialOperator,)

    def get(self, request, account_id):
        tenant = operator_tenant(request)
        account = get_object_or_404(
            get_user_model().objects.filter(tenant_account_q(tenant)), pk=account_id
        )
        return Response(
            {
                "account_ref": str(account.pk),
                "authority": "SIMULATION_PROJECTION",
                "real_financial_mutations_enabled": False,
                "history_counts": list(
                    TransactionHistoryEntry.objects.filter(
                        tenant_id=tenant, account=account, simulation=True
                    )
                    .values("type")
                    .annotate(count=Count("entry_id"))
                    .order_by("type")
                ),
            }
        )


class OperatorStatementIssue(APIView):
    permission_classes = (IsFinancialManager,)

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request, account_id):
        tenant = operator_tenant(request)
        command, error = _command_context(request)
        if error:
            return error
        key, request_id, correlation_id, _ = command
        account = get_object_or_404(
            get_user_model().objects.filter(tenant_account_q(tenant)), pk=account_id
        )
        try:
            period_start = serializers.DateTimeField().to_internal_value(
                request.data.get("period_start")
            )
            period_end = serializers.DateTimeField().to_internal_value(
                request.data.get("period_end")
            )
        except Exception as exc:
            raise ValidationError("Invalid statement period") from exc
        supersedes = None
        if request.data.get("supersedes"):
            supersedes = get_object_or_404(
                Statement,
                pk=request.data["supersedes"],
                tenant_id=tenant,
                account=account,
            )
        payload = {"account_id": account_id, "period_start": period_start, "period_end": period_end, "supersedes": str(supersedes.pk) if supersedes else None, "reason": request.data.get("reason", "")}
        try:
            record, created = _begin_command(request, tenant=tenant, key=key, payload=payload)
        except IdempotencyConflict:
            return Response({"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}, status=409)
        if not created:
            return _replay(record)
        try:
            statement = issue_simulation_statement(
                tenant_id=tenant,
                account=account,
                period_start=period_start,
                period_end=period_end,
                actor=request.user,
                supersedes=supersedes,
                reason=request.data.get("reason", ""),
            )
        except (ValueError, PermissionError) as exc:
            record.delete()
            raise ValidationError("Statement cannot be issued") from exc
        body = StatementSerializer(statement).data
        _application_audit(request, action="operations.statement.issued", resource_type="statement", resource_id=statement.pk, request_id=request_id, correlation_id=correlation_id, reason=request.data.get("reason", "statement issue"), context={"tenant_id": tenant, "account_id": str(account_id), "version": statement.version})
        complete_idempotent_request(record, status=201, body=body, resource_type="statement", resource_id=statement.pk)
        return Response(body, status=201)


class OperatorControlState(APIView):
    permission_classes = (IsAnyOperator,)

    def get(self, request):
        tenant = operator_tenant(request)
        halt = TradingHalt.objects.filter(
            tenant_id=tenant, released_at__isnull=True
        ).values("halt_id", "reason", "activated_at").first()
        return Response(
            {
                "safety_flags": REAL_FEATURE_FLAGS,
                "trading": {"simulation": True, "emergency_halt": halt},
                "providers": {
                    "custody": "DISABLED",
                    "payment": "DISABLED",
                    "execution": "DISABLED",
                },
                "support_impersonation": False,
            }
        )


class OperatorTradingHalt(APIView):
    permission_classes = (IsOperationsManager,)

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        tenant = operator_tenant(request)
        command, error = _command_context(request)
        if error:
            return error
        key, request_id, correlation_id, _ = command
        reason = request.data.get("reason", "").strip()
        if not reason:
            raise ValidationError("A reason is required")
        try:
            record, command_created = _begin_command(request, tenant=tenant, key=key, payload={"reason": reason})
        except IdempotencyConflict:
            return Response({"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}, status=409)
        if not command_created:
            return _replay(record)
        halt, created = TradingHalt.objects.get_or_create(
            tenant_id=tenant,
            released_at__isnull=True,
            defaults={"reason": reason[:500], "activated_by": request.user},
        )
        if created:
            AuditEvent.objects.create(
                tenant_id=tenant,
                actor=request.user,
                role="operations_manager",
                action="TRADING_HALT_ACTIVATED",
                target=f"trading_halt:{halt.pk}",
                reason=halt.reason,
            )
        response_status = 201 if created else 200
        body = {"halt_id": str(halt.pk), "active": True}
        _application_audit(request, action="operations.trading.halted", resource_type="trading_halt", resource_id=halt.pk, request_id=request_id, correlation_id=correlation_id, reason=reason, context={"tenant_id": tenant, "created": created})
        complete_idempotent_request(record, status=response_status, body=body, resource_type="trading_halt", resource_id=halt.pk)
        return Response(body, status=response_status)


class OperatorIncidents(APIView):
    permission_classes = (IsAnyOperator,)

    def get(self, request):
        tenant = operator_tenant(request)
        roles = operator_roles(request)
        payload = {}
        if "platform_admin" in roles or roles & {
            "security_viewer", "security_analyst", "security_manager"
        }:
            payload["security"] = {
                "unresolved_high_risk_events": SecurityEvent.objects.filter(
                    tenant_id=tenant,
                    resolved=False,
                    risk_level__in={"HIGH", "CRITICAL"},
                ).count(),
                "open_fraud_cases": FraudCase.objects.filter(
                    tenant_id=tenant,
                    status__in={"OPEN", "IN_REVIEW", "ESCALATED"},
                ).count(),
            }
        if "platform_admin" in roles or roles & {
            "support_viewer", "support_agent", "support_manager"
        }:
            payload["support"] = {
                "open_cases": SupportCase.objects.filter(
                    tenant_id=tenant,
                    status__in={"OPEN", "PENDING_CUSTOMER", "PENDING_INTERNAL", "ESCALATED"},
                ).count()
            }
        if "platform_admin" in roles or roles & {
            "compliance_viewer", "compliance_analyst", "compliance_manager"
        }:
            payload["compliance"] = {
                "pending_accounts": get_user_model().objects.filter(
                    tenant_account_q(tenant), verification_status="PENDING"
                ).count()
            }
        if "platform_admin" in roles or roles & {
            "operations_viewer", "operations_engineer", "operations_manager"
        }:
            payload["operations"] = {
                "failed_reports": ReportJob.objects.filter(
                    tenant_id=tenant, status="FAILED"
                ).count(),
                "failed_privacy_exports": PrivacyExportJob.objects.filter(
                    tenant_id=tenant, status="FAILED"
                ).count(),
                "notification_dead_letters": Notification.objects.filter(
                    tenant_id=tenant, status="FAILED"
                ).count(),
                "reconciliation_failures": ReconciliationCheck.objects.filter(
                    tenant_id=tenant, status="FAIL"
                ).count(),
            }
        return Response(payload)


class OperatorAuditTimeline(generics.ListAPIView):
    permission_classes = (IsAnyOperator,)

    def get(self, request):
        roles = operator_roles(request)
        queryset = AuditEvent.objects.filter(tenant_id=operator_tenant(request))
        if "platform_admin" not in roles:
            allowed = Q(pk__isnull=True)
            if roles & {"support_viewer", "support_agent", "support_manager"}:
                allowed |= Q(action__startswith="SUPPORT_")
            if roles & {"security_viewer", "security_analyst", "security_manager"}:
                allowed |= Q(action__startswith="ACCOUNT_") | Q(action__startswith="FRAUD_") | Q(action__startswith="SESSION_")
            if roles & {"compliance_viewer", "compliance_analyst", "compliance_manager"}:
                allowed |= Q(action__startswith="LEGAL_HOLD_") | Q(action__startswith="COMPLIANCE_") | Q(action__startswith="PRIVACY_")
            if roles & {"financial_viewer", "financial_operations", "financial_manager"}:
                allowed |= Q(action__startswith="REPORT_") | Q(action__startswith="STATEMENT_") | Q(action__startswith="FINANCIAL_")
            if roles & {"operations_viewer", "operations_engineer", "operations_manager"}:
                allowed |= Q(action__startswith="OPERATOR_") | Q(action__startswith="TRADING_HALT_") | Q(action__startswith="RECONCILIATION_")
            queryset = queryset.filter(allowed)
        rows = queryset.order_by("-timestamp").values(
            "audit_id", "action", "target", "timestamp", "role"
        )[:100]
        return Response(list(rows))


class OperatorReconciliation(APIView):
    permission_classes = (IsManagerOperator,)

    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self, request):
        tenant = operator_tenant(request)
        command, error = _command_context(request)
        if error:
            return error
        key, request_id, correlation_id, _ = command
        try:
            record, created = _begin_command(request, tenant=tenant, key=key, payload={"operation": "OPERATIONS_RECONCILIATION"})
        except IdempotencyConflict:
            return Response({"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was reused with different command semantics."}, status=409)
        if not created:
            return _replay(record)
        checks = reconcile_operational_domains(tenant_id=tenant)
        body = [{"domain": item.domain, "status": item.status} for item in checks]
        _application_audit(request, action="operations.reconciliation.completed", resource_type="operations_reconciliation", resource_id=record.pk, request_id=request_id, correlation_id=correlation_id, reason="operator reconciliation", context={"tenant_id": tenant, "statuses": {item.domain: item.status for item in checks}})
        complete_idempotent_request(record, status=200, body=body, resource_type="operations_reconciliation", resource_id=record.pk)
        return Response(body)
