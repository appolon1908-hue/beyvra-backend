import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timedelta, timezone as datetime_timezone

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from users.serializers import PasswordResetConfirmSerializer
from users.views import LoginView

from apps.compliance.api import _profile
from integrations.models import OrganizationMembership
from notifications.models import NotificationEvent
from trade.models import Trade
from trade.demo_engine import DemoOrderView as EngineDemoOrderView
from wallet.models import Wallet

from .models import (
    AccountSecurityEvent,
    AccountSession,
    ApiIdempotencyRecord,
    NotificationPreference,
    OperatorAction,
    PlatformAuditEvent,
    PlatformOutboxEvent,
    PrivacyRequest,
    ReportExport,
    SupportCase,
    SupportMessage,
    WebhookDeadLetter,
    WebhookInboxEvent,
)
from .serializers import (
    DisabledFeatureSerializer,
    FeatureSerializer,
    ListEnvelopeSerializer,
    MeSerializer,
    OperatorActionSerializer,
    OperatorActionPageSerializer,
    PrivacyRequestSerializer,
    PrivacyRequestPageSerializer,
    ReportExportSerializer,
    StatusSerializer,
    SupportCaseSerializer,
    SupportCasePageSerializer,
    SupportMessageSerializer,
    WebhookAckSerializer,
    WebhookEventSerializer,
)
from .metrics import api_idempotency_total, webhook_latency_seconds, webhooks_total


SAFE_MESSAGES = {
    "AUTHENTICATION_REQUIRED": "Authentication is required.",
    "PERMISSION_DENIED": "You do not have permission to perform this action.",
    "NOT_FOUND": "The requested resource was not found.",
    "VALIDATION_ERROR": "The submitted information is invalid.",
    "IDEMPOTENCY_KEY_REQUIRED": "An idempotency key is required.",
    "IDEMPOTENCY_CONFLICT": "The idempotency key was used with different information.",
    "FEATURE_DISABLED": "This feature is not enabled.",
    "PROVIDER_NOT_AVAILABLE": "The service is temporarily unavailable.",
    "INVALID_WEBHOOK": "Webhook authentication failed.",
    "WEBHOOK_REPLAY_CONFLICT": "The webhook event conflicts with an earlier delivery.",
}


class ProviderWebhookThrottle(ScopedRateThrottle):
    """Keep the provider bound active even when test settings disable defaults."""

    def get_rate(self):
        return self.THROTTLE_RATES.get(self.scope, "300/minute")


IDEMPOTENCY_PARAMETER = OpenApiParameter("Idempotency-Key", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True, description="Unique mutation key. Reuse with a different body returns IDEMPOTENCY_CONFLICT.")


def api_error(code, status_code, *, fields=None):
    body = {"error": {"code": code, "message": SAFE_MESSAGES.get(code, "The request could not be completed.")}}
    if fields:
        body["error"]["fields"] = fields
    return Response(body, status=status_code)


def tenant_for(request, *, roles=None):
    query = OrganizationMembership.objects.select_related("organization").filter(
        user=request.user, organization__is_active=True
    )
    if roles:
        query = query.filter(role__in=roles)
    membership = query.order_by("organization_id").first()
    return membership.organization if membership else None


def page(request, query, serializer):
    try:
        limit = int(request.query_params.get("limit", 50))
    except (TypeError, ValueError):
        return api_error("VALIDATION_ERROR", 400, fields={"limit": ["Enter an integer."]})
    if limit < 1 or limit > 100:
        return api_error("VALIDATION_ERROR", 400, fields={"limit": ["Must be between 1 and 100."]})
    cursor = request.query_params.get("cursor")
    if cursor:
        try:
            cursor = query.model._meta.pk.to_python(cursor)
        except (DjangoValidationError, TypeError, ValueError):
            return api_error("VALIDATION_ERROR", 400, fields={"cursor": ["Invalid cursor."]})
        query = query.filter(pk__lt=cursor)
    rows = list(query.order_by("-pk")[: limit + 1])
    return Response({"results": [serializer(row) for row in rows[:limit]], "next": str(rows[limit - 1].pk) if len(rows) > limit else None})


def request_digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def idempotency_lookup(request, organization, scope):
    metric_scope = "support.message" if scope.startswith("support.case.") else scope
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 255:
        api_idempotency_total.labels(scope=metric_scope, result="missing").inc()
        return None, api_error("IDEMPOTENCY_KEY_REQUIRED", 400)
    digest = request_digest(request.data)
    record, created = ApiIdempotencyRecord.objects.get_or_create(
        organization=organization,
        user=request.user,
        scope=scope,
        key=key,
        defaults={
            "request_hash": digest,
            "response_status": 0,
            "response_body": {},
            "expires_at": timezone.now() + timedelta(days=1),
        },
    )
    if not created:
        if record.request_hash != digest:
            api_idempotency_total.labels(scope=metric_scope, result="conflict").inc()
            return None, api_error("IDEMPOTENCY_CONFLICT", 409)
        if not record.response_status:
            api_idempotency_total.labels(scope=metric_scope, result="in_progress").inc()
            return None, api_error("CONFLICT", 409)
        api_idempotency_total.labels(scope=metric_scope, result="replay").inc()
        return record, Response(record.response_body, status=record.response_status)
    api_idempotency_total.labels(scope=metric_scope, result="claimed").inc()
    return record, None


def remember_idempotency(request, organization, scope, token, response):
    token.response_status = response.status_code
    token.response_body = json.loads(json.dumps(response.data, cls=DjangoJSONEncoder))
    token.save(update_fields=["response_status", "response_body"])


class MeView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = MeSerializer

    def get(self, request):
        organization = tenant_for(request)
        return Response({
            "id": str(request.user.pk),
            "email": None if request.user.is_guest_demo else request.user.email,
            "display_name": request.user.get_full_name(),
            "tenant_id": str(organization.pk) if organization else None,
            "mfa_enabled": bool(request.user.is_mfa_enabled),
        })


class PasswordResetView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = get_user_model().objects.get(pk=force_str(urlsafe_base64_decode(uid)))
        except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, token):
            return api_error("VALIDATION_ERROR", 400)
        user.set_password(serializer.validated_data["new_password"])
        user._password_changed = True
        user.save()
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)
        return Response({"status": "password_updated"})


class CanonicalLoginView(LoginView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code >= 400:
            return api_error("AUTHENTICATION_REQUIRED" if response.status_code == 401 else "VALIDATION_ERROR", response.status_code)
        if response.status_code == 200 and response.data.get("refresh"):
            refresh = RefreshToken(response.data["refresh"])
            authenticated_user = get_user_model().objects.get(pk=refresh["user_id"])
            membership = OrganizationMembership.objects.select_related("organization").filter(user=authenticated_user, organization__is_active=True).order_by("organization_id").first()
            organization = membership.organization if membership else None
            if organization:
                AccountSession.objects.update_or_create(
                    token_jti_hash=hashlib.sha256(str(refresh["jti"]).encode()).hexdigest(),
                    defaults={
                        "organization": organization,
                        "user": authenticated_user,
                        "device_label": (request.headers.get("User-Agent", "Unknown device").split(" ", 1)[0])[:120],
                        "last_seen_at": timezone.now(),
                        "expires_at": datetime.fromtimestamp(int(refresh["exp"]), tz=datetime_timezone.utc),
                    },
                )
        return response


class CanonicalLogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        raw = str(request.data.get("refresh", ""))
        try:
            refresh = RefreshToken(raw)
            if str(refresh.get("user_id")) != str(request.user.pk):
                return api_error("PERMISSION_DENIED", 403)
            digest = hashlib.sha256(str(refresh["jti"]).encode()).hexdigest()
            refresh.blacklist()
        except TokenError:
            return api_error("VALIDATION_ERROR", 400)
        AccountSession.objects.filter(token_jti_hash=digest, user=request.user, revoked_at__isnull=True).update(revoked_at=timezone.now())
        return Response({"status": "logged_out"})


class MfaDisableView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        if not request.user.check_password(str(request.data.get("password", ""))):
            return api_error("VALIDATION_ERROR", 400)
        request.user.is_mfa_enabled = False
        request.user.two_factor_authentication_enabled = False
        request.user.mfa_secret = ""
        request.user.save(update_fields=["is_mfa_enabled", "two_factor_authentication_enabled", "mfa_secret", "updated_at"])
        return Response({"mfa_enabled": False})


class MfaSetupView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        return __import__("users.views", fromlist=["EnableMFAView"]).EnableMFAView().get(request)


class AccountView(MeView):
    allowed = {"first_name", "last_name", "preferred_language", "hidden_account_balances_toggle_enabled"}

    def patch(self, request):
        unknown = set(request.data) - self.allowed
        if unknown:
            return api_error("VALIDATION_ERROR", 400, fields={key: ["Unknown field."] for key in sorted(unknown)})
        for key, value in request.data.items():
            setattr(request.user, key, value)
        request.user.save(update_fields=[*request.data.keys(), "updated_at"])
        return self.get(request)


class AccountSessionCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ListEnvelopeSerializer

    def get(self, request):
        organization = tenant_for(request)
        query = AccountSession.objects.filter(organization=organization, user=request.user, revoked_at__isnull=True)
        return page(request, query, lambda x: {"id": str(x.pk), "device_label": x.device_label, "last_seen_at": x.last_seen_at, "expires_at": x.expires_at})


class AccountSessionDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def delete(self, request, session_id):
        organization = tenant_for(request)
        session = AccountSession.objects.filter(pk=session_id, organization=organization, user=request.user).first()
        if not session:
            return api_error("NOT_FOUND", 404)
        if session.revoked_at is None:
            session.revoked_at = timezone.now()
            session.save(update_fields=["revoked_at", "updated_at"])
            AccountSecurityEvent.objects.create(organization=organization, user=request.user, event_type="SESSION_REVOKED", safe_context={"session_ref": str(session.pk)})
        return Response(status=204)


class AccountSecurityEventView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ListEnvelopeSerializer

    def get(self, request):
        organization = tenant_for(request)
        query = AccountSecurityEvent.objects.filter(organization=organization, user=request.user)
        return page(request, query, lambda x: {"id": str(x.pk), "event_type": x.event_type, "created_at": x.created_at})


class ComplianceRestrictionView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ListEnvelopeSerializer

    def get(self, request):
        profile = _profile(request)
        if not profile:
            return Response({"results": [], "next": None})
        now = timezone.now()
        rows = profile.restrictions.filter(active=True).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).order_by("-created_at")
        return Response({"results": [{"restriction_id": str(x.pk), "type": x.restriction_type, "reason_code": x.reason_code, "expires_at": x.expires_at} for x in rows], "next": None})


class FeatureDisabledView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = DisabledFeatureSerializer

    def get(self, request, *args, **kwargs):
        return api_error("FEATURE_DISABLED", 503)

    def post(self, request, *args, **kwargs):
        return api_error("FEATURE_DISABLED", 503)


class DemoAccountView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        organization = tenant_for(request)
        wallet = Wallet.objects.filter(user=request.user, organization=organization, is_real=False, is_archived=False).first()
        if not wallet:
            return api_error("NOT_FOUND", 404)
        return Response({"id": str(wallet.pk), "kind": "DEMO", "currency": "VIRTUAL_USD", "balance": str(wallet.balance), "real_money": False})


class DemoWalletsView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ListEnvelopeSerializer

    def get(self, request):
        organization = tenant_for(request)
        rows = Wallet.objects.filter(user=request.user, organization=organization, is_real=False, is_archived=False).order_by("id")
        return Response({"results": [{"id": str(x.pk), "name": x.name, "currency": "VIRTUAL_USD", "balance": str(x.balance), "real_money": False} for x in rows], "next": None})


class DemoPositionsView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ListEnvelopeSerializer

    def get(self, request):
        organization = tenant_for(request)
        rows = Trade.objects.filter(organization=organization, wallet__user=request.user, wallet__is_real=False, demo_state="OPEN").select_related("asset").order_by("-id")
        return Response({"results": [{"id": str(x.pk), "instrument": x.asset.symbol, "side": x.trade_type.upper(), "quantity": str(x.quantity), "state": x.demo_state} for x in rows], "next": None})


class DemoOrderCollectionView(EngineDemoOrderView):
    """Canonical collection contract while retaining the proven demo create engine."""

    serializer_class = ListEnvelopeSerializer

    def get(self, request):
        organization = tenant_for(request)
        rows = Trade.objects.filter(
            organization=organization,
            wallet__user=request.user,
            wallet__is_real=False,
        ).select_related("asset").order_by("-created_at", "-id")
        return page(request, rows, self._data)


class NotificationCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ListEnvelopeSerializer

    def get(self, request):
        organization = tenant_for(request)
        query = NotificationEvent.objects.filter(user=request.user, organization=organization)
        return page(request, query, lambda x: {"id": str(x.pk), "title": x.title, "message": x.message, "category": x.category, "payload": x.payload, "read": x.is_read, "is_read": x.is_read, "created_at": x.created_at})


class NotificationReadView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, notification_id):
        organization = tenant_for(request)
        row = NotificationEvent.objects.filter(pk=notification_id, user=request.user, organization=organization).first()
        if not row:
            return api_error("NOT_FOUND", 404)
        if not row.is_read:
            row.is_read = True
            row.save(update_fields=["is_read"])
        return Response({"id": str(row.pk), "read": True})


class NotificationReadAllView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        organization = tenant_for(request)
        updated = NotificationEvent.objects.filter(user=request.user, organization=organization, is_read=False).update(is_read=True)
        return Response({"updated": updated})


class NotificationPreferenceView(APIView):
    permission_classes = (IsAuthenticated,)

    def _row(self, request):
        organization = tenant_for(request)
        return NotificationPreference.objects.get_or_create(organization=organization, user=request.user)[0]

    def get(self, request):
        row = self._row(request)
        return Response({"email_enabled": row.email_enabled, "in_app_enabled": row.in_app_enabled, "categories": row.categories})

    def patch(self, request):
        allowed = {"email_enabled", "in_app_enabled", "categories"}
        if set(request.data) - allowed:
            return api_error("VALIDATION_ERROR", 400)
        row = self._row(request)
        for key, value in request.data.items():
            setattr(row, key, value)
        row.save()
        return self.get(request)


def support_data(row, include_messages=False):
    data = {"id": str(row.pk), "subject": row.subject, "status": row.status, "created_at": row.created_at, "updated_at": row.updated_at}
    if include_messages:
        data["messages"] = [{"id": str(x.pk), "body": x.body, "created_at": x.created_at} for x in row.messages.filter(customer_visible=True).order_by("created_at")]
    return data


class SupportCaseCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = SupportCasePageSerializer

    def get(self, request):
        organization = tenant_for(request)
        return page(request, SupportCase.objects.filter(organization=organization, user=request.user), support_data)

    @extend_schema(request=SupportCaseSerializer, responses={201: SupportCaseSerializer}, parameters=[IDEMPOTENCY_PARAMETER])
    @transaction.atomic
    def post(self, request):
        organization = tenant_for(request)
        subject = str(request.data.get("subject", "")).strip()
        message = str(request.data.get("message", "")).strip()
        if not subject or len(subject) > 160 or not message or len(message) > 4000:
            return api_error("VALIDATION_ERROR", 400)
        token, replay = idempotency_lookup(request, organization, "support.case.create")
        if replay:
            return replay
        row = SupportCase.objects.create(organization=organization, user=request.user, subject=subject)
        SupportMessage.objects.create(organization=organization, user=request.user, case=row, body=message)
        PlatformOutboxEvent.objects.create(organization=organization, event_type="support.case.created.v1", aggregate_type="support_case", aggregate_ref=str(row.pk), payload={"case_id": str(row.pk)})
        response = Response(support_data(row, True), status=201)
        remember_idempotency(request, organization, "support.case.create", token, response)
        return response


class SupportCaseDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = SupportCaseSerializer

    def get(self, request, case_id):
        row = SupportCase.objects.filter(pk=case_id, organization=tenant_for(request), user=request.user).first()
        return Response(support_data(row, True)) if row else api_error("NOT_FOUND", 404)


class SupportMessageView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = SupportMessageSerializer

    @extend_schema(request=SupportMessageSerializer, responses={201: SupportMessageSerializer}, parameters=[IDEMPOTENCY_PARAMETER])
    @transaction.atomic
    def post(self, request, case_id):
        organization = tenant_for(request)
        row = SupportCase.objects.filter(pk=case_id, organization=organization, user=request.user).first()
        if not row:
            return api_error("NOT_FOUND", 404)
        body = str(request.data.get("body", "")).strip()
        if not body or len(body) > 4000:
            return api_error("VALIDATION_ERROR", 400)
        token, replay = idempotency_lookup(request, organization, f"support.case.{case_id}.message")
        if replay:
            return replay
        message = SupportMessage.objects.create(organization=organization, user=request.user, case=row, body=body)
        PlatformOutboxEvent.objects.create(organization=organization, event_type="support.message.created.v1", aggregate_type="support_case", aggregate_ref=str(row.pk), payload={"case_id": str(row.pk), "message_id": str(message.pk)})
        response = Response({"id": str(message.pk), "body": message.body, "created_at": message.created_at}, status=201)
        remember_idempotency(request, organization, f"support.case.{case_id}.message", token, response)
        return response


REPORT_TYPES = {"activity", "trades", "fees", "transactions", "statements"}


class ReportView(APIView):
    permission_classes = (IsAuthenticated,)
    report_type = None

    def get(self, request, report_type=None):
        report_type = report_type or self.report_type
        if report_type not in REPORT_TYPES:
            return api_error("NOT_FOUND", 404)
        # Real financial reports remain Financial Service-owned and disabled.
        # These public reports expose only the tenant's authoritative simulation
        # records and label every entry accordingly.
        if report_type in {"fees", "statements"}:
            return Response({"results": [], "next": None, "report_type": report_type, "timezone": "UTC", "simulation": True})
        organization = tenant_for(request)
        rows = Trade.objects.filter(
            organization=organization,
            wallet__user=request.user,
            wallet__is_real=False,
        ).select_related("asset", "transaction")
        for parameter, lookup in (("created_after", "created_at__gte"), ("created_before", "created_at__lte")):
            value = request.query_params.get(parameter)
            if not value:
                continue
            parsed = parse_datetime(value)
            if parsed is None or timezone.is_naive(parsed):
                return api_error("VALIDATION_ERROR", 400, fields={parameter: ["Use an ISO-8601 timestamp with timezone."]})
            rows = rows.filter(**{lookup: parsed})
        status_filter = request.query_params.get("status")
        if status_filter:
            rows = rows.filter(demo_state=status_filter.upper())
        instrument = request.query_params.get("instrument") or request.query_params.get("asset")
        if instrument:
            rows = rows.filter(asset__symbol=instrument.upper())

        def report_data(row):
            return {
                "id": str(row.pk),
                "type": "TRADE",
                "asset": row.asset.symbol,
                "instrument": row.asset.symbol,
                "side": row.trade_type.upper(),
                "quantity": str(row.quantity),
                "price": str(row.price_per_unit),
                "amount": str(row.total_value),
                "fee": "0",
                "status": row.demo_state,
                "occurred_at": row.created_at,
                "settled_at": row.result_time,
                "source_ref": str(row.transaction.transaction_id),
                "simulation": True,
            }

        return page(request, rows, report_data)


class ReportExportCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ReportExportSerializer

    @extend_schema(request=ReportExportSerializer, responses={202: ReportExportSerializer}, parameters=[IDEMPOTENCY_PARAMETER])
    @transaction.atomic
    def post(self, request):
        organization = tenant_for(request)
        report_type = str(request.data.get("type", ""))
        if report_type not in REPORT_TYPES:
            return api_error("VALIDATION_ERROR", 400)
        token, replay = idempotency_lookup(request, organization, "report.export.create")
        if replay:
            return replay
        row = ReportExport.objects.create(organization=organization, user=request.user, report_type=report_type, filters=request.data.get("filters", {}), idempotency_key=token.key)
        PlatformOutboxEvent.objects.create(organization=organization, event_type="report.export.requested.v1", aggregate_type="report_export", aggregate_ref=str(row.pk), payload={"export_id": str(row.pk), "report_type": report_type})
        response = Response({"id": str(row.pk), "type": row.report_type, "status": row.status, "created_at": row.created_at}, status=202)
        remember_idempotency(request, organization, "report.export.create", token, response)
        return response


class ReportExportDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ReportExportSerializer

    def get(self, request, export_id):
        row = ReportExport.objects.filter(pk=export_id, organization=tenant_for(request), user=request.user).first()
        return Response({"id": str(row.pk), "type": row.report_type, "status": row.status, "created_at": row.created_at}) if row else api_error("NOT_FOUND", 404)


def privacy_data(row):
    return {"id": str(row.pk), "type": row.request_type, "status": row.status, "created_at": row.created_at}


class PrivacyRequestCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PrivacyRequestPageSerializer

    def get(self, request):
        organization = tenant_for(request)
        return page(request, PrivacyRequest.objects.filter(organization=organization, user=request.user), privacy_data)

    @transaction.atomic
    def create(self, request, request_type):
        organization = tenant_for(request)
        scope = f"privacy.{request_type.lower()}"
        token, replay = idempotency_lookup(request, organization, scope)
        if replay:
            return replay
        row = PrivacyRequest.objects.create(organization=organization, user=request.user, request_type=request_type, idempotency_key=token.key)
        PlatformAuditEvent.objects.create(organization=organization, actor=request.user, event_type="PRIVACY_REQUEST_CREATED", subject_type="privacy_request", subject_ref=str(row.pk))
        PlatformOutboxEvent.objects.create(organization=organization, event_type="privacy.request.created.v1", aggregate_type="privacy_request", aggregate_ref=str(row.pk), payload={"request_id": str(row.pk), "type": request_type})
        response = Response(privacy_data(row), status=202)
        remember_idempotency(request, organization, scope, token, response)
        return response


class PrivacyExportView(PrivacyRequestCollectionView):
    @extend_schema(request=None, responses={202: PrivacyRequestSerializer}, parameters=[IDEMPOTENCY_PARAMETER])
    def post(self, request):
        return self.create(request, "EXPORT")


class PrivacyDeletionView(PrivacyRequestCollectionView):
    @extend_schema(request=None, responses={202: PrivacyRequestSerializer}, parameters=[IDEMPOTENCY_PARAMETER])
    def post(self, request):
        return self.create(request, "DELETION")


class PrivacyRequestDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = PrivacyRequestSerializer

    def get(self, request, request_id):
        row = PrivacyRequest.objects.filter(pk=request_id, organization=tenant_for(request), user=request.user).first()
        return Response(privacy_data(row)) if row else api_error("NOT_FOUND", 404)


OPERATOR_ROLES = ("operations", "platform_admin", "compliance_manager", "security", "financial")


class OperatorActionCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = OperatorActionPageSerializer

    def get(self, request):
        organization = tenant_for(request, roles=OPERATOR_ROLES)
        if not organization:
            return api_error("PERMISSION_DENIED", 403)
        query = OperatorAction.objects.filter(organization=organization)
        return page(request, query, lambda x: {"id": str(x.pk), "action_type": x.action_type, "target_ref": x.target_ref, "status": x.status, "created_at": x.created_at})

    @extend_schema(request=OperatorActionSerializer, responses={201: OperatorActionSerializer}, parameters=[IDEMPOTENCY_PARAMETER])
    @transaction.atomic
    def post(self, request):
        organization = tenant_for(request, roles=OPERATOR_ROLES)
        if not organization:
            return api_error("PERMISSION_DENIED", 403)
        action_type = str(request.data.get("action_type", ""))[:64]
        target_ref = str(request.data.get("target_ref", ""))[:255]
        reason = str(request.data.get("reason", ""))[:500]
        if not action_type or not target_ref or len(reason) < 8:
            return api_error("VALIDATION_ERROR", 400)
        token, replay = idempotency_lookup(request, organization, "operator.action.create")
        if replay:
            return replay
        row = OperatorAction.objects.create(organization=organization, action_type=action_type, target_ref=target_ref, reason=reason, requested_by=request.user)
        PlatformAuditEvent.objects.create(organization=organization, actor=request.user, event_type="OPERATOR_ACTION_REQUESTED", subject_type="operator_action", subject_ref=str(row.pk), safe_metadata={"action_type": action_type})
        PlatformOutboxEvent.objects.create(organization=organization, event_type="operator.action.requested.v1", aggregate_type="operator_action", aggregate_ref=str(row.pk), payload={"action_id": str(row.pk), "action_type": action_type})
        response = Response({"id": str(row.pk), "status": row.status}, status=201)
        remember_idempotency(request, organization, "operator.action.create", token, response)
        return response


class OperatorActionApproveView(APIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = OperatorActionSerializer

    @transaction.atomic
    def post(self, request, action_id):
        organization = tenant_for(request, roles=("platform_admin",))
        if not organization:
            return api_error("PERMISSION_DENIED", 403)
        row = OperatorAction.objects.select_for_update().filter(pk=action_id, organization=organization).first()
        if not row:
            return api_error("NOT_FOUND", 404)
        if row.requested_by_id == request.user.pk:
            return api_error("PERMISSION_DENIED", 403)
        if row.status != "PENDING_APPROVAL":
            return api_error("CONFLICT", 409)
        row.status = "APPROVED"
        row.approved_by = request.user
        row.approved_at = timezone.now()
        row.save(update_fields=["status", "approved_by", "approved_at"])
        PlatformAuditEvent.objects.create(organization=organization, actor=request.user, event_type="OPERATOR_ACTION_APPROVED", subject_type="operator_action", subject_ref=str(row.pk), safe_metadata={"action_type": row.action_type})
        PlatformOutboxEvent.objects.create(organization=organization, event_type="operator.action.approved.v1", aggregate_type="operator_action", aggregate_ref=str(row.pk), payload={"action_id": str(row.pk), "action_type": row.action_type})
        return Response({"id": str(row.pk), "status": row.status})


class StatusView(APIView):
    permission_classes = (AllowAny,)
    serializer_class = StatusSerializer

    def get(self, request):
        return Response({"status": "operational", "server_time": timezone.now(), "api_version": "v1"})


class FeatureView(APIView):
    permission_classes = (AllowAny,)
    serializer_class = FeatureSerializer

    def get(self, request):
        return Response({"features": {
            "real_wallet_read": False,
            "real_deposits": False,
            "real_withdrawals": False,
            "real_internal_transfers": False,
            "real_trading": False,
            "external_execution": False,
            "real_money": False,
            "demo_trading": bool(getattr(settings, "PAPER_TRADING_ONLY", True)),
            "five_second_market_data": False,
        }})


class ProviderWebhookView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (ProviderWebhookThrottle,)
    throttle_scope = "provider_webhook"
    max_body = 262144
    event_id_pattern = re.compile(r"[A-Za-z0-9:_.-]{1,255}")
    serializer_class = WebhookAckSerializer

    @extend_schema(request=WebhookEventSerializer, responses={200: WebhookAckSerializer, 202: WebhookAckSerializer})
    def post(self, request, provider, purpose):
        started = time.monotonic()
        configured = getattr(settings, "PLATFORM_WEBHOOK_SECRETS", {})
        provider_label = provider if isinstance(configured, dict) and provider in configured else "unknown"
        purpose_label = purpose if f"{provider}:{purpose}" in getattr(settings, "PLATFORM_WEBHOOK_EVENT_TYPES", {}) else "unknown"
        webhooks_total.labels(provider=provider_label, webhook_type=purpose_label, result="received").inc()
        def observed(response, result):
            webhooks_total.labels(provider=provider_label, webhook_type=purpose_label, result=result).inc()
            webhook_latency_seconds.labels(provider=provider_label, webhook_type=purpose_label).observe(time.monotonic() - started)
            return response
        if len(request.body) > self.max_body:
            return observed(api_error("VALIDATION_ERROR", 413), "oversized")
        secrets = configured
        candidates = secrets.get(provider, []) if isinstance(secrets, dict) else []
        if isinstance(candidates, str):
            candidates = [candidates]
        event_id = request.headers.get("X-Beyvra-Event-ID", "")
        signature = request.headers.get("X-Beyvra-Signature", "")
        try:
            timestamp = int(request.headers.get("X-Beyvra-Timestamp", "0"))
        except ValueError:
            timestamp = 0
        now = int(time.time())
        if not candidates:
            return observed(api_error("PROVIDER_NOT_AVAILABLE", 503), "provider_unavailable")
        if not self.event_id_pattern.fullmatch(event_id) or timestamp > now + 30 or timestamp < now - 300:
            return observed(api_error("INVALID_WEBHOOK", 401), "signature_failure")
        signed = f"{provider}.{purpose}.{timestamp}.{event_id}.".encode() + request.body
        if not any(hmac.compare_digest(hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest(), signature) for secret in candidates if secret):
            return observed(api_error("INVALID_WEBHOOK", 401), "signature_failure")
        payload_hash = hashlib.sha256(request.body).hexdigest()
        existing = WebhookInboxEvent.objects.filter(provider=provider, purpose=purpose, provider_event_id=event_id).first()
        if existing:
            return observed(Response({"status": "duplicate"}), "duplicate") if existing.payload_hash == payload_hash else observed(api_error("WEBHOOK_REPLAY_CONFLICT", 409), "replay_conflict")
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return observed(api_error("VALIDATION_ERROR", 400), "malformed")
        if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
            return observed(api_error("VALIDATION_ERROR", 400), "malformed")
        try:
            with transaction.atomic():
                inbox = WebhookInboxEvent.objects.create(provider=provider, purpose=purpose, provider_event_id=event_id, payload_hash=payload_hash)
                supported = getattr(settings, "PLATFORM_WEBHOOK_EVENT_TYPES", {}).get(f"{provider}:{purpose}", [])
                if payload["type"] not in supported:
                    inbox.result = "DEAD_LETTER"
                    inbox.processed_at = timezone.now()
                    inbox.save(update_fields=["result", "processed_at"])
                    WebhookDeadLetter.objects.create(inbox_event=inbox, error_code="UNKNOWN_EVENT_TYPE")
                    return observed(Response({"status": "ignored"}, status=202), "dead_letter")
                inbox.result = "ACCEPTED"
                inbox.processed_at = timezone.now()
                inbox.save(update_fields=["result", "processed_at"])
        except IntegrityError:
            existing = WebhookInboxEvent.objects.get(provider=provider, purpose=purpose, provider_event_id=event_id)
            return observed(Response({"status": "duplicate"}), "duplicate") if existing.payload_hash == payload_hash else observed(api_error("WEBHOOK_REPLAY_CONFLICT", 409), "replay_conflict")
        return observed(Response({"status": "accepted"}, status=202), "accepted")
