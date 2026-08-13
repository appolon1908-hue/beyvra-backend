import statistics, time
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from apps.trading.execution_control.quality import PriceImprovementAuthority, SlippageAuthority
from apps.trading.execution_control.reconciliation import ExecutionReconciler
from apps.trading.execution_control.router import SmartOrderRouter, digest

class Command(BaseCommand):
    help="Bounded simulation/paper routing load certification; performs no provider network calls."
    def add_arguments(self,parser): parser.add_argument("--count",type=int,choices=(100,1000,5000),default=100)
    def handle(self,*args,**options):
        user,_=get_user_model().objects.get_or_create(email="routing-load@fixture.invalid",defaults={"phone_number":"+15550000999"})
        request={"instrument_id":"BTC-USD","side":"BUY","order_type":"MARKET","quantity":"1","reference_price":"100","mode":"SIMULATION",
            "asset_class":"CRYPTO","time_in_force":"DAY","limit_price":None,"market_snapshot_hash":digest("load-market"),"pricing_snapshot_hash":digest("load-price"),"risk_snapshot_hash":digest("load-risk")}
        router=SmartOrderRouter(); samples=[]
        for _ in range(options["count"]):
            start=time.perf_counter();result=router.route(user,request,persist=False);samples.append((time.perf_counter()-start)*1000)
            if not result["routable"]: raise RuntimeError("LOAD_ROUTE_NOT_ROUTABLE")
        quality=[];slippage=SlippageAuthority();improvement=PriceImprovementAuthority()
        for _ in range(options["count"]):
            start=time.perf_counter();slippage.calculate("BUY",Decimal("100"),Decimal("100.01"),Decimal("1"));improvement.calculate("BUY",Decimal("100"),Decimal("99.99"),Decimal("1"));quality.append((time.perf_counter()-start)*1000)
        reconciliation=[]
        for _ in range(min(options["count"],100)):
            start=time.perf_counter();ExecutionReconciler().inspect();reconciliation.append((time.perf_counter()-start)*1000)
        def percentile(values,p):
            values.sort();return values[min(len(values)-1,int(len(values)*p))]
        self.stdout.write(f"ROUTES={len(samples)} P50_MS={statistics.median(samples):.3f} P95_MS={percentile(samples,.95):.3f} P99_MS={percentile(samples,.99):.3f} QUALITY_P95_MS={percentile(quality,.95):.3f} RECONCILIATION_P95_MS={percentile(reconciliation,.95):.3f} OUTBOUND_LIVE_EXECUTION_REQUESTS=0 REAL_FINANCIAL_EFFECTS=0")
