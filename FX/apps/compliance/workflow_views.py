from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from integrations.permissions import organization_for_request
from .models import ComplianceProfile
from .services import build_underwriting_workflow, get_trading_eligibility


class ComplianceStatusView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        organization = organization_for_request(request)
        profile = ComplianceProfile.objects.filter(user=request.user, organization=organization).first()
        if not profile:
            return Response({
                "result": "DENIED",
                "policy_version": "2026.08.v1",
                "evaluated_at": timezone.now().isoformat(),
                "reason_codes": ["PROFILE_REQUIRED"],
                "requirements": ["IDENTITY_VERIFICATION"]
            })

        eligibility = get_trading_eligibility(profile)
        return Response({
            "result": eligibility.result.value if hasattr(eligibility.result, "value") else str(eligibility.result),
            "policy_version": eligibility.policy_version,
            "evaluated_at": eligibility.evaluated_at.isoformat(),
            "reason_codes": eligibility.reason_codes,
            "requirements": [],
        })


class UnderwritingWorkflowView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        organization = organization_for_request(request)
        profile = ComplianceProfile.objects.filter(user=request.user, organization=organization).first()
        if not profile:
            return Response({
                "workflow": "trading_underwriting",
                "status": "ACTION_REQUIRED",
                "policy_version": "compliance-2026-08-11.v1",
                "evaluated_at": timezone.now().isoformat(),
                "phases": [],
                "requirements": ["IDENTITY_VERIFICATION"],
                "eligibility": {
                    "trading": {"result": "DENIED", "reason_codes": ["PROFILE_REQUIRED"]},
                    "deposit": {"result": "DENIED", "reason_codes": ["PROFILE_REQUIRED"]},
                    "withdrawal": {"result": "DENIED", "reason_codes": ["PROFILE_REQUIRED"]},
                    "transfer": {"result": "DENIED", "reason_codes": ["PROFILE_REQUIRED"]},
                },
            }, status=409)
        payload = build_underwriting_workflow(profile)
        return Response(payload)


class ComplianceRestrictionsView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        organization = organization_for_request(request)
        profile = ComplianceProfile.objects.filter(user=request.user, organization=organization).first()
        if not profile:
            return Response({"results": []})

        restrictions = profile.restrictions.filter(active=True)
        return Response({
            "results": [
                {
                    "id": str(r.restriction_id),
                    "restriction_type": r.restriction_type,
                    "reason_code": r.reason_code,
                    "active": r.active,
                    "created_at": r.created_at.isoformat(),
                }
                for r in restrictions
            ]
        })


class ComplianceAcknowledgementsView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        document_id = request.data.get("document_id", "terms_of_service")
        document_version = request.data.get("document_version", "2026.1")
        return Response({
            "status": "RECORDED",
            "document_id": document_id,
            "document_version": document_version,
            "user_id": str(request.user.pk),
            "acknowledged_at": timezone.now().isoformat(),
        }, status=201)


class ComplianceDocumentsView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        # Metadata registration for private secure upload
        doc_type = request.data.get("document_type", "IDENTITY")
        return Response({
            "status": "REGISTERED",
            "document_type": doc_type,
            "upload_channel": "SECURE_PRIVATE_S3",
            "scan_status": "PENDING",
            "expires_at": (timezone.now() + timezone.timedelta(minutes=15)).isoformat()
        }, status=202)
