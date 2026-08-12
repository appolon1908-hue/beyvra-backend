from rest_framework import permissions, response, status, views
from .models import CostBasisPosition, PortfolioNavSnapshot, RealizedPnLEvent, TaxLot, UnrealizedPnLSnapshot, ValuationPrice


def account_ref(request): return f"sim:{request.user.pk}"
class Base(views.APIView): permission_classes=(permissions.IsAuthenticated,)
class Prices(Base):
 def get(self,r,instrument_id):
  rows=ValuationPrice.objects.filter(instrument_id=instrument_id).order_by("-valuation_time")[:100]
  return response.Response({"results":[{"id":str(x.id),"instrument_id":x.instrument_id,"valuation_time":x.valuation_time,"price":str(x.price),"currency":x.currency,"price_type":x.price_type,"quality_state":x.quality_state} for x in rows]})
class CostBasis(Base):
 def get(self,r,instrument_id=None):
  rows=CostBasisPosition.objects.filter(account_ref=account_ref(r)); rows=rows.filter(instrument_id=instrument_id) if instrument_id else rows
  return response.Response({"results":[{"instrument_id":x.instrument_id,"quantity":str(x.quantity),"total_cost_basis":str(x.total_cost_basis),"average_unit_cost":str(x.average_unit_cost),"currency":x.currency} for x in rows]})
class Lots(Base):
 def get(self,r,lot_id=None):
  rows=TaxLot.objects.filter(account_ref=account_ref(r)); rows=rows.filter(pk=lot_id) if lot_id else rows
  return response.Response({"results":[{"id":str(x.id),"instrument_id":x.instrument_id,"remaining_quantity":str(x.remaining_quantity),"unit_cost":str(x.unit_cost),"status":x.status,"policy_version":x.policy_version} for x in rows]})
class Pnl(Base):
 model=None
 def get(self,r,instrument_id=None):
  rows=self.model.objects.filter(account_ref=account_ref(r)); rows=rows.filter(instrument_id=instrument_id) if instrument_id else rows
  field="realized_pnl" if self.model is RealizedPnLEvent else "unrealized_pnl"
  return response.Response({"results":[{"instrument_id":x.instrument_id,field:str(getattr(x,field)),"currency":x.currency} for x in rows]})
class Realized(Pnl): model=RealizedPnLEvent
class Unrealized(Pnl): model=UnrealizedPnLSnapshot
class Nav(Base):
 def get(self,r):
  rows=PortfolioNavSnapshot.objects.filter(account_ref=account_ref(r)).order_by("-valuation_time")[:100]
  return response.Response({"results":[{"id":str(x.id),"nav":str(x.nav),"base_currency":x.base_currency,"valuation_time":x.valuation_time,"quality_state":x.quality_state,"simulation":x.simulation} for x in rows]})
class Disabled(Base):
 def get(self,r,*a,**k): return response.Response({"code":"FEATURE_DISABLED"},status=503)
 def post(self,r,*a,**k): return self.get(r)
