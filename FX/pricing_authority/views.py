from django.utils import timezone
from rest_framework import generics, permissions, response, status, views

from .models import AccountPlan, AccountPlanAssignment, PlanEntitlement
from .serializers import FeePreviewSerializer, PlanSerializer
from .services import calculate_fee


class PlanListView(generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = PlanSerializer
    queryset = AccountPlan.objects.filter(status="ACTIVE").order_by("code")


class CurrentPlanView(views.APIView):
    permission_classes = (permissions.IsAuthenticated,)
    def get(self, request):
        assignment = AccountPlanAssignment.objects.filter(account=request.user, status="ACTIVE", effective_to__isnull=True).select_related("plan_version__plan").first()
        if not assignment: return response.Response({"code":"PLAN_NOT_ASSIGNED"}, status=404)
        return response.Response(PlanSerializer(assignment.plan_version.plan).data)


class EntitlementsView(views.APIView):
    permission_classes = (permissions.IsAuthenticated,)
    def get(self, request):
        assignment = AccountPlanAssignment.objects.filter(account=request.user, status="ACTIVE", effective_to__isnull=True).first()
        if not assignment: return response.Response({"results": []})
        rows = PlanEntitlement.objects.filter(plan_version=assignment.plan_version, enabled=True).select_related("entitlement")
        return response.Response({"results":[{"entitlement": x.entitlement.code, "state":"LIMITED" if x.limit_value is not None else "ALLOW", "limit":str(x.limit_value) if x.limit_value is not None else None, "unit":x.limit_unit} for x in rows]})


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
