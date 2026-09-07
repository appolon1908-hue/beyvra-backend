from django.utils import timezone
from django.utils.dateparse import parse_datetime
from integrations.permissions import organization_for_request
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from .models import ComplianceProfile, ComplianceProviderGovernance
from .providers import DisabledComplianceProvider
import hashlib, hmac, json, re, time
from datetime import timedelta
from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.permissions import AllowAny
from .models import ComplianceInboxEvent, ComplianceProfile
from .services import transition_kyc
from .domain import KycState
from .domain import AmlState, JurisdictionState, SanctionsState
from .metrics import event_processing_failures_total, provider_failures_total, webhook_signature_failures_total
from .services import effective_profile_states, transition_aml, transition_jurisdiction, transition_sanctions
from .serializers import ComplianceProfileResponseSerializer, ComplianceRequirementsResponseSerializer, SafeComplianceErrorEnvelopeSerializer

SAFE_REQUIREMENT_ACTIONS={"IDENTITY_VERIFICATION":"Complete identity verification.","ADDRESS_VERIFICATION":"Provide address verification.","SOURCE_OF_FUNDS":"Provide the requested source-of-funds information.","TAX_INFORMATION":"Provide the requested tax information.","MANUAL_REVIEW":"No action is required while your account is reviewed."}

def _profile(request):
    organization = organization_for_request(request)
    return ComplianceProfile.objects.filter(user=request.user, organization=organization).first()

class ComplianceProfileView(APIView):
    permission_classes = (IsAuthenticated,)
    @extend_schema(responses={200:ComplianceProfileResponseSerializer,409:SafeComplianceErrorEnvelopeSerializer})
    def get(self, request):
        p = _profile(request)
        if not p: return Response({"error": {"code": "COMPLIANCE_PROFILE_REQUIRED", "message": "Compliance setup is required."}}, status=409)
        now = timezone.now(); restrictions = p.restrictions.filter(active=True).filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now)); states=effective_profile_states(p,now)
        return Response({**states,"restrictions":[{"restriction_id":str(x.pk),"type":x.restriction_type,"reason_code":x.reason_code,"expires_at":x.expires_at} for x in restrictions],"requirements":[x.type for x in p.requirements.filter(required=True).exclude(status="COMPLETED")],"last_updated":p.updated_at})

from django.db import models
class ComplianceRequirementsView(APIView):
    permission_classes = (IsAuthenticated,)
    @extend_schema(responses={200:ComplianceRequirementsResponseSerializer})
    def get(self, request):
        p = _profile(request)
        if not p: return Response({"results": []})
        return Response({"results":[{"requirement_id":str(x.pk),"type":x.type,"status":x.status,"required":x.required,"deadline":x.deadline,"user_action":SAFE_REQUIREMENT_ACTIONS.get(x.type,"Provide the requested verification information.")} for x in p.requirements.all()]})

class KycSessionView(APIView):
    permission_classes = (IsAuthenticated,)
    @extend_schema(request=None,responses={503:SafeComplianceErrorEnvelopeSerializer})
    def post(self, request):
        approved = ComplianceProviderGovernance.objects.filter(state="PRODUCTION_APPROVED").first()
        if not approved: return Response({"error":{"code":"PROVIDER_NOT_AVAILABLE","message":"Verification is temporarily unavailable."}}, status=503)
        try: DisabledComplianceProvider().create_session(str(request.user.pk))
        except RuntimeError:
            provider_failures_total.labels(operation="create_session").inc()
            return Response({"error":{"code":"PROVIDER_NOT_AVAILABLE","message":"Verification is temporarily unavailable."}}, status=503)
        return Response({"error":{"code":"PROVIDER_NOT_AVAILABLE","message":"Verification is temporarily unavailable."}}, status=503)

class ComplianceWebhookView(APIView):
    authentication_classes = (); permission_classes = (AllowAny,)
    def post(self, request, provider_key):
        secret = settings.COMPLIANCE_WEBHOOK_SECRET
        try: timestamp = int(request.headers.get("X-Compliance-Timestamp", "0"))
        except ValueError: timestamp = 0
        signature = request.headers.get("X-Compliance-Signature", "")
        event_id = request.headers.get("X-Compliance-Event-ID", "")
        if not secret or not re.fullmatch(r"[A-Za-z0-9:_.-]{1,255}",event_id) or abs(int(time.time()) - timestamp) > settings.COMPLIANCE_WEBHOOK_MAX_AGE_SECONDS:
            webhook_signature_failures_total.inc()
            return Response({"error":{"code":"INVALID_WEBHOOK"}}, status=401)
        signed = provider_key.encode()+b"."+str(timestamp).encode()+b"."+event_id.encode()+b"."+request.body
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            webhook_signature_failures_total.inc()
            return Response({"error":{"code":"INVALID_WEBHOOK"}}, status=401)
        if not ComplianceProviderGovernance.objects.filter(provider_key=provider_key, state__in=("STAGING_APPROVED","PRODUCTION_APPROVED")).exists(): return Response({"error":{"code":"PROVIDER_NOT_AVAILABLE"}}, status=503)
        try:
            payload=json.loads(request.body or b"{}")
        except (ValueError,TypeError): return Response({"error":{"code":"INVALID_WEBHOOK"}},status=400)
        if not isinstance(payload,dict):return Response({"error":{"code":"INVALID_WEBHOOK"}},status=400)
        payload_hash=hashlib.sha256(request.body).hexdigest()
        existing=ComplianceInboxEvent.objects.filter(provider=provider_key,provider_event_id=event_id).first()
        if existing:
            return Response({"status":"duplicate"},status=200) if existing.payload_hash==payload_hash else Response({"error":{"code":"WEBHOOK_REPLAY_CONFLICT"}},status=409)
        try:
            with transaction.atomic():
                inbox=ComplianceInboxEvent.objects.create(provider=provider_key, provider_event_id=event_id, payload_hash=payload_hash)
                if payload.get("type") not in ("verification.updated","aml.updated","sanctions.updated","jurisdiction.updated"):raise ValueError("INVALID_PROVIDER_RESULT")
                if payload.get("type") in ("verification.updated","aml.updated","sanctions.updated","jurisdiction.updated"):
                    occurred_at=parse_datetime(str(payload.get("occurred_at","")))
                    now=timezone.now()
                    if not occurred_at or timezone.is_naive(occurred_at) or occurred_at > now + timedelta(seconds=settings.COMPLIANCE_WEBHOOK_MAX_AGE_SECONDS) or occurred_at < now - timedelta(seconds=settings.COMPLIANCE_PROVIDER_RESULT_MAX_AGE_SECONDS): raise ValueError("STALE_PROVIDER_RESULT")
                    profile=ComplianceProfile.objects.filter(pk=payload.get("account_ref")).first()
                    reference=str(payload.get("evidence_ref") or payload.get("verification_ref", ""))[:255]
                    if not profile or not reference: raise ValueError("INVALID_PROVIDER_RESULT")
                    mappings={
                        "verification.updated":{"pending":KycState.PENDING,"review":KycState.IN_REVIEW,"approved":KycState.APPROVED,"rejected":KycState.REJECTED,"expired":KycState.EXPIRED},
                        "aml.updated":{"pending":AmlState.PENDING,"clear":AmlState.CLEARED,"review":AmlState.REVIEW_REQUIRED,"blocked":AmlState.BLOCKED},
                        "sanctions.updated":{"clear":SanctionsState.CLEAR,"possible_match":SanctionsState.POSSIBLE_MATCH,"confirmed_match":SanctionsState.CONFIRMED_MATCH,"review":SanctionsState.MANUAL_REVIEW},
                        "jurisdiction.updated":{"supported":JurisdictionState.SUPPORTED,"limited":JurisdictionState.LIMITED,"restricted":JurisdictionState.RESTRICTED,"unknown":JurisdictionState.UNKNOWN},
                    }
                    result=mappings[payload["type"]].get(payload.get("result"))
                    if not result: raise ValueError("INVALID_PROVIDER_RESULT")
                    transitions={"verification.updated":transition_kyc,"aml.updated":transition_aml,"sanctions.updated":transition_sanctions,"jurisdiction.updated":transition_jurisdiction}
                    transitions[payload["type"]](profile.pk,result,actor_ref=f"PROVIDER:{provider_key}",evidence_ref=reference)
                inbox.processed_at=timezone.now(); inbox.save(update_fields=["processed_at"])
        except IntegrityError:
            existing=ComplianceInboxEvent.objects.filter(provider=provider_key,provider_event_id=event_id).first()
            return Response({"status":"duplicate"},status=200) if existing and existing.payload_hash==payload_hash else Response({"error":{"code":"WEBHOOK_REPLAY_CONFLICT"}},status=409)
        except ValueError as exc:
            event_processing_failures_total.labels(stage="provider_result").inc()
            code="STALE_PROVIDER_RESULT" if str(exc)=="STALE_PROVIDER_RESULT" else "INVALID_PROVIDER_RESULT"
            return Response({"error":{"code":code}},status=409)
        return Response({"status":"accepted"}, status=202)
