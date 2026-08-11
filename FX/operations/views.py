from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AccountFreeze,
    AccountSession,
    AuditEvent,
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
from .permissions import IsSecurityManager, IsSupportOperator
from .serializers import (
    CustomerSupportEventSerializer,
    NotificationSerializer,
    PreferenceSerializer,
    PrivacyExportSerializer,
    ReportJobSerializer,
    StatementSerializer,
    SupportCaseSerializer,
    SupportMessageSerializer,
    TransactionSerializer,
)
from .services import REAL_FEATURE_FLAGS, approve_operator_request, stable_hash, tenant_for


class TenantMixin:
    def tenant_id(self):
        return tenant_for(self.request.user)


class SupportCaseListCreate(TenantMixin, generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = SupportCaseSerializer

    def get_queryset(self):
        return SupportCase.objects.filter(tenant_id=self.tenant_id(), account=self.request.user).order_by("-created_at")

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
            tenant_id=self.tenant_id(), actor=self.request.user, action="SUPPORT_CASE_CREATED", target=str(case.pk)
        )


class SupportCaseDetail(TenantMixin, generics.RetrieveAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = SupportCaseSerializer
    lookup_url_kwarg = "case_id"
    lookup_field = "case_id"

    def get_queryset(self):
        return SupportCase.objects.filter(tenant_id=self.tenant_id(), account=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        case = self.get_object()
        data = self.get_serializer(case).data
        events = case.timeline.filter(visibility="CUSTOMER_VISIBLE_MESSAGE").order_by("created_at")
        data["timeline"] = CustomerSupportEventSerializer(events, many=True).data
        return Response(data)


class SupportMessageCreate(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, case_id):
        serializer = SupportMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = get_object_or_404(SupportCase, case_id=case_id, tenant_id=self.tenant_id(), account=request.user)
        event = SupportCaseEvent.objects.create(
            tenant_id=self.tenant_id(),
            account=request.user,
            case=case,
            event_type="CUSTOMER_RESPONSE",
            visibility="CUSTOMER_VISIBLE_MESSAGE",
            body_safe=serializer.validated_data["message"],
            actor=request.user,
        )
        return Response(CustomerSupportEventSerializer(event).data, status=status.HTTP_201_CREATED)


class TransactionList(TenantMixin, generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = TransactionSerializer

    def get_queryset(self):
        qs = TransactionHistoryEntry.objects.filter(tenant_id=self.tenant_id(), account=self.request.user)
        if self.request.query_params.get("date_from"):
            qs = qs.filter(occurred_at__gte=self.request.query_params["date_from"])
        if self.request.query_params.get("date_to"):
            qs = qs.filter(occurred_at__lte=self.request.query_params["date_to"])
        return qs


class NotificationList(TenantMixin, generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(tenant_id=self.tenant_id(), account=self.request.user).order_by(
            "-created_at"
        )


class NotificationRead(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, notification_id):
        updated = Notification.objects.filter(
            notification_id=notification_id, tenant_id=self.tenant_id(), account=request.user
        ).update(read_at=timezone.now(), status="READ")
        if not updated:
            raise NotFound("Resource not found")
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationReadAll(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        Notification.objects.filter(tenant_id=self.tenant_id(), account=request.user, read_at__isnull=True).update(
            read_at=timezone.now(), status="READ"
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PreferenceList(TenantMixin, generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PreferenceSerializer

    def get_queryset(self):
        return NotificationPreference.objects.filter(tenant_id=self.tenant_id(), account=self.request.user)

    def perform_create(self, serializer):
        category = serializer.validated_data["category"]
        if category in {"SECURITY", "FINANCIAL"} and not serializer.validated_data.get("enabled", True):
            serializer.validated_data["enabled"] = True
        serializer.save(tenant_id=self.tenant_id(), account=self.request.user)

    def patch(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.validated_data["category"]
        enabled = serializer.validated_data.get("enabled", True)
        if category in {"SECURITY", "FINANCIAL"} and not enabled:
            return Response(
                {"code": "MANDATORY_NOTIFICATION", "message": "This notification is required for account safety."},
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
        return ReportJob.objects.filter(tenant_id=self.tenant_id(), account=self.request.user).order_by("-created_at")

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        report_type = request.data.get("report_type", "ACTIVITY")
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                {"code": "IDEMPOTENCY_KEY_REQUIRED", "message": "An idempotency key is required."}, status=400
            )
        job, created = ReportJob.objects.get_or_create(
            tenant_id=self.tenant_id(),
            account=request.user,
            idempotency_key=idempotency_key,
            defaults={"report_type": report_type, "parameters_hash": stable_hash(request.data)},
        )
        return Response(self.get_serializer(job).data, status=201 if created else 200)


class StatementList(TenantMixin, generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = StatementSerializer

    def get_queryset(self):
        return Statement.objects.filter(
            tenant_id=self.tenant_id(), account=self.request.user, reconciliation_passed=True
        ).order_by("-period_end", "-version")


class PrivacyExportListCreate(TenantMixin, generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PrivacyExportSerializer

    def get_queryset(self):
        return PrivacyExportJob.objects.filter(tenant_id=self.tenant_id(), account=self.request.user).order_by(
            "-created_at"
        )

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            return Response(
                {"code": "IDEMPOTENCY_KEY_REQUIRED", "message": "An idempotency key is required."}, status=400
            )
        job, created = PrivacyExportJob.objects.get_or_create(
            tenant_id=self.tenant_id(),
            account=request.user,
            idempotency_key=key,
            defaults={"policy_version": "PENDING-LEGAL-APPROVAL"},
        )
        return Response(self.get_serializer(job).data, status=201 if created else 200)


class SessionList(TenantMixin, generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = None

    def get(self, request):
        rows = AccountSession.objects.filter(
            tenant_id=self.tenant_id(), account=request.user, revoked_at__isnull=True, expires_at__gt=timezone.now()
        ).values("session_id", "created_at", "last_seen_at", "expires_at", "auth_strength", "mfa_verified_at")
        return Response(list(rows))


class SessionRevoke(TenantMixin, APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, session_id):
        updated = AccountSession.objects.filter(
            session_id=session_id, tenant_id=self.tenant_id(), account=request.user, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())
        if not updated:
            raise NotFound("Resource not found")
        AuditEvent.objects.create(
            tenant_id=self.tenant_id(), actor=request.user, action="SESSION_REVOKED", target=str(session_id)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SafetyFlags(APIView):
    permission_classes = (IsSupportOperator,)

    def get(self, request):
        return Response(REAL_FEATURE_FLAGS)


class OperatorFreeze(APIView):
    permission_classes = (IsSecurityManager,)

    @transaction.atomic
    def post(self, request, account_id):
        tenant = request.headers.get("X-Beyvra-Tenant", tenant_for(request.user)).lower()
        level = request.data.get("level", "FULL")
        if level not in {"PARTIAL", "FULL"}:
            return Response({"code": "INVALID_FREEZE_LEVEL", "message": "The requested action is invalid."}, status=400)
        freeze, _ = AccountFreeze.objects.update_or_create(
            tenant_id=tenant,
            account_id=account_id,
            released_at__isnull=True,
            defaults={
                "level": level,
                "reason_code": request.data.get("reason_code", "ACCOUNT_REVIEW_REQUIRED"),
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
    permission_classes = (IsAuthenticated,)

    def post(self, request, request_id):
        tenant = request.headers.get("X-Beyvra-Tenant", tenant_for(request.user)).lower()
        roles = set(OperatorRole.objects.filter(user=request.user, tenant_id=tenant).values_list("role", flat=True))
        try:
            action = approve_operator_request(request_id=request_id, approver=request.user, approver_roles=roles)
        except (PermissionError, OperatorActionRequest.DoesNotExist):
            return Response(
                {"code": "ACTION_NOT_ALLOWED", "message": "The requested action is not available."}, status=403
            )
        return Response({"request_id": action.request_id, "status": "APPROVED"})
