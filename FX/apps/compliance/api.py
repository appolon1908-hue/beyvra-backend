from django.utils import timezone
from integrations.models import OrganizationMembership
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ComplianceProfile, ComplianceProviderGovernance
from .providers import DisabledComplianceProvider
import hashlib, hmac, json, time
from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.permissions import AllowAny
from .models import ComplianceInboxEvent

def _profile(request):
    org_id = OrganizationMembership.objects.filter(user=request.user).order_by("id").values_list("organization_id", flat=True).first()
    if not org_id: return None
    return ComplianceProfile.objects.filter(user=request.user, organization_id=org_id).first()

class ComplianceProfileView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        p = _profile(request)
        if not p: return Response({"error": {"code": "COMPLIANCE_PROFILE_REQUIRED", "message": "Compliance setup is required."}}, status=409)
        now = timezone.now(); restrictions = p.restrictions.filter(active=True).filter(models.Q(expires_at__isnull=True)|models.Q(expires_at__gt=now))
        return Response({"kyc_state":p.kyc_state,"aml_state":p.aml_state,"sanctions_state":p.sanctions_state,"jurisdiction_state":p.jurisdiction_state,"account_state":p.account_state,"restrictions":[{"restriction_id":str(x.pk),"type":x.restriction_type,"reason_code":x.reason_code,"expires_at":x.expires_at} for x in restrictions],"requirements":[x.type for x in p.requirements.filter(required=True).exclude(status="COMPLETED")],"last_updated":p.updated_at})

from django.db import models
class ComplianceRequirementsView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        p = _profile(request)
        if not p: return Response({"results": []})
        return Response({"results":[{"requirement_id":str(x.pk),"type":x.type,"status":x.status,"required":x.required,"deadline":x.deadline,"user_action":x.user_action} for x in p.requirements.all()]})

class KycSessionView(APIView):
    permission_classes = (IsAuthenticated,)
    def post(self, request):
        approved = ComplianceProviderGovernance.objects.filter(state="PRODUCTION_APPROVED").first()
        if not approved: return Response({"error":{"code":"PROVIDER_NOT_AVAILABLE","message":"Verification is temporarily unavailable."}}, status=503)
        try: DisabledComplianceProvider().create_session(str(request.user.pk))
        except RuntimeError: return Response({"error":{"code":"PROVIDER_NOT_AVAILABLE","message":"Verification is temporarily unavailable."}}, status=503)

class ComplianceWebhookView(APIView):
    authentication_classes = (); permission_classes = (AllowAny,)
    def post(self, request, provider_key):
        secret = settings.COMPLIANCE_WEBHOOK_SECRET
        try: timestamp = int(request.headers.get("X-Compliance-Timestamp", "0"))
        except ValueError: timestamp = 0
        signature = request.headers.get("X-Compliance-Signature", "")
        if not secret or abs(int(time.time()) - timestamp) > settings.COMPLIANCE_WEBHOOK_MAX_AGE_SECONDS: return Response({"error":{"code":"INVALID_WEBHOOK"}}, status=401)
        expected = hmac.new(secret.encode(), str(timestamp).encode()+b"."+request.body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature): return Response({"error":{"code":"INVALID_WEBHOOK"}}, status=401)
        if not ComplianceProviderGovernance.objects.filter(provider_key=provider_key, state__in=("STAGING_APPROVED","PRODUCTION_APPROVED")).exists(): return Response({"error":{"code":"PROVIDER_NOT_AVAILABLE"}}, status=503)
        event_id = request.headers.get("X-Compliance-Event-ID", "")
        if not event_id: return Response({"error":{"code":"INVALID_WEBHOOK"}}, status=400)
        try:
            with transaction.atomic(): ComplianceInboxEvent.objects.create(provider=provider_key, provider_event_id=event_id, payload_hash=hashlib.sha256(request.body).hexdigest(), processed_at=timezone.now())
        except IntegrityError: return Response({"status":"duplicate"}, status=200)
        return Response({"status":"accepted"}, status=202)
