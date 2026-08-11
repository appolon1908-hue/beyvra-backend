import statistics, time
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
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
        samples.sort(); percentile=lambda p:samples[min(len(samples)-1,int(len(samples)*p))]
        self.stdout.write(f"ROUTES={len(samples)} P50_MS={statistics.median(samples):.3f} P95_MS={percentile(.95):.3f} P99_MS={percentile(.99):.3f} OUTBOUND_LIVE_EXECUTION_REQUESTS=0 REAL_FINANCIAL_EFFECTS=0")
