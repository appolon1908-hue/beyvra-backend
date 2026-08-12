from decimal import Decimal
from apps.trading.execution_authority import record_quality

class SlippageAuthority:
    def calculate(self,side,reference,vwap,quantity):
        reference=Decimal(reference); vwap=Decimal(vwap); quantity=Decimal(quantity)
        per_unit=(vwap-reference) if side=="BUY" else (reference-vwap)
        return {"per_unit":per_unit,"amount":per_unit*quantity,"bps":per_unit/reference*Decimal("10000")}

class PriceImprovementAuthority:
    def calculate(self,side,benchmark,vwap,quantity):
        result=SlippageAuthority().calculate(side,benchmark,vwap,quantity)
        return {"per_unit":-result["per_unit"],"amount":-result["amount"],"bps":-result["bps"]}

class ExecutionQualityAuthority:
    def report(self,order): return record_quality(order)
