from decimal import Decimal, InvalidOperation
from rest_framework import permissions, response, status, views
from .models import CollateralPolicy, ExposureLimit, MarginCall, MarginPolicy
from .services import BuyingPowerService, CollateralService, ExposureService, LiquidationPlanner, MarginHealthService, MarginRequirementService


def d(value):
    try:return Decimal(str(value))
    except (InvalidOperation,TypeError):raise ValueError


class BaseRiskView(views.APIView): permission_classes=(permissions.IsAuthenticated,)
class SummaryView(BaseRiskView):
 def get(self,r): return response.Response({"simulation":True,"real_margin_enabled":False,"margin_health":"UNKNOWN","liquidation_eligible":False})
class MarginPreview(BaseRiskView):
 def post(self,r):
  policy=MarginPolicy.objects.filter(status="ACTIVE").order_by("-policy_version").first()
  if not policy:return response.Response({"code":"MARGIN_POLICY_UNAVAILABLE"},status=503)
  try:out=MarginRequirementService.calculate(policy=policy,side=r.data.get("side","BUY"),quantity=d(r.data.get("quantity")),price=d(r.data.get("price")))
  except ValueError:return response.Response({"code":"MARGIN_CALCULATION_FAILED"},status=400)
  return response.Response({k:str(v) if isinstance(v,Decimal) else v for k,v in out.items()})
class CollateralPreview(BaseRiskView):
 def post(self,r):
  policy=CollateralPolicy.objects.filter(asset=r.data.get("asset"),status="ACTIVE").first()
  if not policy:return response.Response({"code":"FEATURE_DISABLED"},status=503)
  try:out=CollateralService.preview(policy=policy,quantity=d(r.data.get("quantity")),price=d(r.data.get("price")),fresh=bool(r.data.get("fresh",True)))
  except ValueError:return response.Response({"code":"REFERENCE_DATA_UNAVAILABLE"},status=400)
  return response.Response({k:str(v) if isinstance(v,Decimal) else v for k,v in out.items()})
class BuyingPowerPreview(BaseRiskView):
 def post(self,r):
  try:s=BuyingPowerService.calculate_snapshot(equity=d(r.data.get("equity")),eligible_collateral=d(r.data.get("eligible_collateral")),initial_margin_used=d(r.data.get("initial_margin_used","0")),reservations=d(r.data.get("reservations","0"))); out=BuyingPowerService.calculate_order_impact(s,d(r.data.get("required_margin")))
  except ValueError:return response.Response({"code":"FEATURE_DISABLED"},status=400)
  return response.Response({k:str(v) if isinstance(v,Decimal) else v for k,v in out.items()})
class ExposurePreview(BaseRiskView):
 def post(self,r):
  limits=ExposureLimit.objects.filter(status="ACTIVE"); out=ExposureService.evaluate_order(current_gross=d(r.data.get("current_gross","0")),order_notional=d(r.data.get("order_notional")),limits=limits)
  return response.Response({k:str(v) if isinstance(v,Decimal) else v for k,v in out.items()})
class MarginHealthView(BaseRiskView):
 def get(self,r): return response.Response({"health_state":"UNKNOWN","simulation":True})
class MarginCallsView(BaseRiskView):
 def get(self,r): return response.Response({"results":[{"id":str(x.id),"state":x.state,"required_amount":str(x.required_amount),"currency":x.currency,"simulation":True} for x in MarginCall.objects.filter(account=r.user)]})
class LiquidationPreview(BaseRiskView):
 def post(self,r): return response.Response(LiquidationPlanner.generate_plan(required_reduction=d(r.data.get("required_reduction")),positions=[]))
class FeatureDisabledView(BaseRiskView):
 def get(self,r,*a,**k):return response.Response({"code":"FEATURE_DISABLED","simulation":True},status=503)
 def post(self,r,*a,**k):return self.get(r)
