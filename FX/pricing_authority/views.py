from django.utils import timezone
from rest_framework import generics, permissions, response, status, views

from integrations.permissions import organization_for_request
from .models import AccountPlan
from .serializers import FeePreviewSerializer, PlanSerializer
from .services import calculate_fee, current_plan_assignment, entitlement_decisions


class PlanListView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = PlanSerializer
    queryset = AccountPlan.objects.filter(status="ACTIVE").order_by("code")


class CurrentPlanView(views.APIView):
    permission_classes = (permissions.IsAuthenticated,)
    def get(self, request):
        organization = organization_for_request(request)
        assignment, _ambiguous = current_plan_assignment(request.user, tenant_ref=str(organization.id))
        if not assignment: return response.Response({"code":"PLAN_NOT_ASSIGNED"}, status=404)
        return response.Response({
            **PlanSerializer(assignment.plan_version.plan).data,
            "tenant_id": str(organization.id),
            "plan_version": assignment.plan_version.version,
        })


class EntitlementsView(views.APIView):
    permission_classes = (permissions.IsAuthenticated,)
    def get(self, request):
        organization = organization_for_request(request)
        decisions = entitlement_decisions(request.user, str(organization.id))
        return response.Response({
            "tenant_id": str(organization.id),
            "results": [{
                "entitlement": item.entitlement_code,
                "state": item.state,
                "limit": str(item.limit) if item.limit is not None else None,
                "unit": item.limit_unit,
                "policy_version": item.effective_policy_version,
                "source": item.source,
            } for item in decisions],
        })


class FeePreviewView(views.APIView):
    permission_classes = (permissions.IsAuthenticated,)
    fixed_fee_type = None
    def post(self, request):
        payload = dict(request.data)
        if self.fixed_fee_type: payload["fee_type"] = self.fixed_fee_type
        serializer = FeePreviewSerializer(data=payload); serializer.is_valid(raise_exception=True)
        try: result = calculate_fee(account=request.user, at=timezone.now(), **serializer.validated_data)
        except ValueError: return response.Response({"code":"FEATURE_NOT_AVAILABLE"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        result["amount"] = str(result["amount"])
        return response.Response(result)


class TradingPreviewView(FeePreviewView): fixed_fee_type="TRADING_COMMISSION"
class WithdrawalPreviewView(FeePreviewView): fixed_fee_type="WITHDRAWAL"
class TransferPreviewView(FeePreviewView): fixed_fee_type="TRANSFER"
