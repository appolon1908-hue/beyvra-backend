import json, math, os, time, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from apps.foundation.models import OutboxEvent
from apps.trading.application.simulation import cancel, create, preview, process_created_order
from apps.trading.models import SimulatedReservation, SimulatedTrade, TradingOrder
from users.models import User

def percentile(values,p):
    if not values:return 0
    values=sorted(values); return values[min(len(values)-1,max(0,int((len(values)-1)*p)))]

class Command(BaseCommand):
    help="Run deterministic simulation load only against an explicitly isolated environment"
    def add_arguments(self,parser):
        parser.add_argument("--workflows",type=int,choices=(100,1000,10000),default=100); parser.add_argument("--concurrency",type=int,default=10); parser.add_argument("--output")
    def handle(self,*_args,**options):
        if os.getenv("BEYVRA_LOAD_ISOLATED")!="1" or settings.DEPLOYMENT_ENV not in {"test","local"}: raise CommandError("ISOLATED_LOAD_TARGET_REQUIRED")
        if any(getattr(settings,x,False) for x in ("REAL_TRADING_ENABLED","EXTERNAL_EXECUTION_ENABLED","REAL_MONEY_ENABLED")): raise CommandError("REAL_FINANCIAL_EFFECTS_REFUSED")
        workflows=options["workflows"]; concurrency=min(max(options["concurrency"],1),50)
        users=[User.objects.create_user(email=f"load-{uuid.uuid4()}@example.invalid",phone_number=f"+1202{uuid.uuid4().int%10000000:07d}",password=None) for _ in range(max(1,math.ceil(workflows/1000)))]
        payload={"instrument":"BTC-USD","side":"BUY","order_type":"MARKET","quantity":"0.0001"}
        timings={k:[] for k in ("preview","order","execution","settlement","outbox")}; errors=[]; started=time.monotonic()
        def workflow(index):
            close_old_connections(); local={}
            try:
                user=users[index%len(users)]
                tick=time.monotonic(); preview(user,payload); local["preview"]=(time.monotonic()-tick)*1000
                tick=time.monotonic(); body,_=create(user,payload,f"load-{index}"); local["order"]=(time.monotonic()-tick)*1000
                scenario="PARTIAL_THEN_FILL" if index%10==0 else "OPEN_THEN_CANCEL" if index%10==1 else "IMMEDIATE_FULL_FILL"
                tick=time.monotonic(); order=process_created_order(body["id"],scenario); local["execution"]=(time.monotonic()-tick)*1000
                if scenario=="OPEN_THEN_CANCEL": cancel(user,order.id)
                local["settlement"]=local["execution"]; local["outbox"]=local["order"]
                return local,None
            except Exception as exc:return local,type(exc).__name__
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for future in as_completed([pool.submit(workflow,i) for i in range(workflows)]):
                result,error=future.result(); errors.extend([error] if error else [])
                for key,value in result.items():timings[key].append(value)
        duration=time.monotonic()-started
        subject_refs=[str(user.pk) for user in users]; order_rows=TradingOrder.objects.filter(subject_ref__in=subject_refs); order_ids=[str(x) for x in order_rows.values_list("id",flat=True)]
        report={"workflows_requested":workflows,"workflows_completed":workflows-len(errors),"concurrency":concurrency,"duration_seconds":round(duration,3),"throughput_per_second":round((workflows-len(errors))/duration,3),"errors":len(errors),"error_categories":sorted(set(errors)),"orders":order_rows.count(),"trades":SimulatedTrade.objects.filter(order__subject_ref__in=subject_refs).count(),"reservations":SimulatedReservation.objects.filter(account__subject_ref__in=subject_refs).count(),"outbox_events":OutboxEvent.objects.filter(tenant_ref="default",aggregate_id__in=order_ids).count(),"latency_ms":{key:{"p50":round(percentile(values,.5),3),"p95":round(percentile(values,.95),3),"p99":round(percentile(values,.99),3)} for key,values in timings.items()}}
        text=json.dumps(report,sort_keys=True); self.stdout.write(text)
        if options["output"]:
            from pathlib import Path
            Path(options["output"]).write_text(text+"\n")
        if errors: raise CommandError("LOAD_CERTIFICATION_ERRORS")
