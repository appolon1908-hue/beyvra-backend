from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
    ReportJob,
    Statement,
    SupportCase,
    SupportCaseEvent,
    TransactionHistoryEntry,
)
from .permissions import (
    IsAnyOperator,
    IsManagerOperator,
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
)
from .services import (
    REAL_FEATURE_FLAGS,
    approve_operator_request,
    deletion_disposition,
    execute_operator_request,
    reconcile_operational_domains,
    revoke_bound_session,
    stable_hash,
    tenant_for,
)


class TenantMixin:
    def tenant_id(self):
        return tenant_for(self.request.user)


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

    @transaction.atomic
    def post(self, request, account_id):
        tenant = request.headers.get(
            "X-Beyvra-Tenant", tenant_for(request.user)
        ).lower()
        account = get_object_or_404(
            get_user_model(), pk=account_id, brand__iexact=tenant
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
        freeze, _ = AccountFreeze.objects.update_or_create(
            tenant_id=tenant,
            account=account,
            released_at__isnull=True,
            defaults={
                "level": level,
                "reason_code": request.data.get(
                    "reason_code", "ACCOUNT_REVIEW_REQUIRED"
                ),
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
        return Response({"level": freeze.level}, status=201)


class OperatorApprove(APIView):
    permission_classes = (IsManagerOperator,)

    def post(self, request, request_id):
        tenant = request.headers.get(
            "X-Beyvra-Tenant", tenant_for(request.user)
        ).lower()
        roles = set(
            OperatorRole.objects.filter(
                user=request.user, tenant_id=tenant
            ).values_list("role", flat=True)
        )
        try:
            action = approve_operator_request(
                request_id=request_id, approver=request.user, approver_roles=roles
            )
        except (PermissionError, OperatorActionRequest.DoesNotExist):
            return Response(
                {
                    "code": "ACTION_NOT_ALLOWED",
                    "message": "The requested action is not available.",
                },
                status=403,
            )
        return Response({"request_id": action.request_id, "status": "APPROVED"})


class OperatorExecute(APIView):
    permission_classes = (IsManagerOperator,)

    def post(self, request, request_id):
        tenant = operator_tenant(request)
        roles = set(
            OperatorRole.objects.filter(
                user=request.user, tenant_id=tenant
            ).values_list("role", flat=True)
        )
        try:
            action = execute_operator_request(
                request_id=request_id, executor=request.user, executor_roles=roles
            )
        except (PermissionError, OperatorActionRequest.DoesNotExist):
            return Response(
                {
                    "code": "ACTION_NOT_ALLOWED",
                    "message": "The requested action is not available.",
                },
                status=403,
            )
        return Response({"request_id": action.request_id, "status": "EXECUTED"})


def operator_tenant(request):
    return request.headers.get("X-Beyvra-Tenant", tenant_for(request.user)).lower()


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
        }:
            return Response(
                {
                    "code": "INVALID_ACTION_TYPE",
                    "message": "The requested action is invalid.",
                },
                status=400,
            )
        reason = request.data.get("reason", "").strip()
        if not reason:
            return Response(
                {"code": "REASON_REQUIRED", "message": "A reason is required."},
                status=400,
            )
        action = OperatorActionRequest.objects.create(
            tenant_id=operator_tenant(request),
            action_type=action_type,
            target_ref=request.data.get("target_ref", "")[:128],
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
        return Response({"request_id": action.pk, "status": action.status}, status=201)


class OperatorLegalHold(APIView):
    permission_classes = (IsManagerOperator,)

    @transaction.atomic
    def post(self, request, account_id):
        tenant = operator_tenant(request)
        account = get_object_or_404(
            get_user_model(), pk=account_id, brand__iexact=tenant
        )
        hold = LegalHold.objects.create(
            tenant_id=tenant,
            account=account,
            reason=request.data.get("reason", "policy hold")[:500],
            created_by=request.user,
        )
        AuditEvent.objects.create(
            tenant_id=hold.tenant_id,
            actor=request.user,
            action="LEGAL_HOLD_CREATED",
            target=str(hold.pk),
            reason=hold.reason,
        )
        return Response({"hold_id": hold.pk, "active": True}, status=201)


class OperatorAuditTimeline(generics.ListAPIView):
    permission_classes = (IsAnyOperator,)

    def get(self, request):
        rows = AuditEvent.objects.filter(tenant_id=operator_tenant(request)).values(
            "audit_id", "action", "target", "timestamp", "role"
        )[:100]
        return Response(list(rows))


class OperatorReconciliation(APIView):
    permission_classes = (IsManagerOperator,)

    def post(self, request):
        checks = reconcile_operational_domains(tenant_id=operator_tenant(request))
        return Response(
            [{"domain": item.domain, "status": item.status} for item in checks]
        )
