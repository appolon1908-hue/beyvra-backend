import json, math, os, time, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from apps.foundation.models import OutboxEvent
from apps.trading.application.simulation import cancel, create, preview, process_created_order, replace
from apps.trading.models import SimulatedPosition, SimulatedReservation, SimulatedTrade, TradingOrder
from apps.trading.tests.fixtures import ensure_paper_settlement_calendar
from apps.compliance.domain import AccountState, AmlState, JurisdictionState, KycState, SanctionsState
from apps.compliance.models import ComplianceProfile
from integrations.models import Organization, OrganizationMembership
from users.models import User

def percentile(values,p):
    if not values:return 0
    values=sorted(values); return values[min(len(values)-1,max(0,int((len(values)-1)*p)))]


def error_category(error):
    value = str(error).upper()
    if any(item in value for item in ("AUTH", "TOKEN", "SESSION")): return "authentication"
    if any(item in value for item in ("TENANT", "ORGANIZATION")): return "tenant_selection"
    if any(item in value for item in ("INSTRUMENT", "FEE_POLICY", "SETTLEMENT_CALENDAR")): return "fixture_setup"
    if any(item in value for item in ("PRICE", "MARKET", "PROVIDER")): return "market_data_authority"
    if any(item in value for item in ("DATABASE", "OPERATIONALERROR", "INTEGRITYERROR")): return "test_database"
    if any(item in value for item in ("VALIDATION", "IDEMPOTENCY", "VERSION", "PRECONDITION")): return "api_contract"
    return "application_exception"

class Command(BaseCommand):
    help="Run deterministic simulation load only against an explicitly isolated environment"
    def add_arguments(self,parser):
        parser.add_argument("--workflows",type=int,choices=(100,1000,10000),default=100); parser.add_argument("--concurrency",type=int,default=10); parser.add_argument("--output")
    def handle(self,*_args,**options):
        if os.getenv("BEYVRA_LOAD_ISOLATED")!="1" or settings.DEPLOYMENT_ENV not in {"test","local"}: raise CommandError("ISOLATED_LOAD_TARGET_REQUIRED")
        safety_flags = (
            "REAL_TRADING_ENABLED", "REAL_MONEY_ENABLED", "REAL_SETTLEMENT_ENABLED",
            "REAL_MARGIN_ENABLED", "REAL_LIQUIDATION_ENABLED", "EXTERNAL_EXECUTION_ENABLED",
            "LIVE_BROKER_ROUTING_ENABLED", "FIX_LIVE_SESSION_ENABLED",
        )
        if any(getattr(settings,x,False) for x in safety_flags): raise CommandError("REAL_FINANCIAL_EFFECTS_REFUSED")
        ensure_paper_settlement_calendar()
        workflows=options["workflows"]; concurrency=min(max(options["concurrency"],1),50)
        organization=Organization.objects.create(name=f"Mission 1 load {uuid.uuid4()}")
        users=[User.objects.create_user(email=f"load-{uuid.uuid4()}@example.invalid",phone_number=f"+1202{uuid.uuid4().int%10000000:07d}",password=None) for _ in range(max(1,math.ceil(workflows/1000)))]
        for user in users:
            OrganizationMembership.objects.create(user=user,organization=organization)
            ComplianceProfile.objects.create(user=user,organization=organization,account_state=AccountState.ACTIVE,kyc_state=KycState.APPROVED,aml_state=AmlState.CLEARED,sanctions_state=SanctionsState.CLEAR,jurisdiction_state=JurisdictionState.SUPPORTED)
        payload={"instrument":"BTC-USD","side":"BUY","order_type":"MARKET","quantity":"0.01"}
        timings={k:[] for k in ("preview","order_create","order_list","position_list","cancel","replace")}; errors=[]; started=time.monotonic()
        def workflow(index):
            close_old_connections(); local={}
            try:
                user=users[index%len(users)]
                tick=time.monotonic(); preview(user,payload); local["preview"]=(time.monotonic()-tick)*1000
                tick=time.monotonic(); body,_=create(user,payload,f"load-{index}"); local["order_create"]=(time.monotonic()-tick)*1000
                process_created_order(body["id"],"IMMEDIATE_FULL_FILL")
                tick=time.monotonic(); list(TradingOrder.objects.filter(subject_ref=str(user.pk)).order_by("-created_at")[:100]); local["order_list"]=(time.monotonic()-tick)*1000
                tick=time.monotonic(); list(SimulatedPosition.objects.filter(account__subject_ref=str(user.pk)).order_by("instrument_id")[:100]); local["position_list"]=(time.monotonic()-tick)*1000
                limit_body,_=create(user,{**payload,"order_type":"LIMIT","quantity":"0.02","limit_price":"99"},f"load-limit-{index}")
                limit_order=process_created_order(limit_body["id"],"OPEN_THEN_CANCEL")
                tick=time.monotonic(); replaced=replace(user,limit_order.id,{"limit_price":"98"},f"load-replace-{index}",limit_order.version); local["replace"]=(time.monotonic()-tick)*1000
                tick=time.monotonic(); cancel(user,limit_order.id,f"load-cancel-{index}",replaced["version"]); local["cancel"]=(time.monotonic()-tick)*1000
                return local,None
            except Exception as exc:return local,f"{type(exc).__name__}:{str(exc)[:96]}"
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for future in as_completed([pool.submit(workflow,i) for i in range(workflows)]):
                result,error=future.result(); errors.extend([error] if error else [])
                for key,value in result.items():timings[key].append(value)
        duration=time.monotonic()-started
        subject_refs=[str(user.pk) for user in users]; order_rows=TradingOrder.objects.filter(subject_ref__in=subject_refs); order_ids=[str(x) for x in order_rows.values_list("id",flat=True)]
        categories={}
        for error in errors:
            category=error_category(error);categories[category]=categories.get(category,0)+1
        report={"workflows_requested":workflows,"workflows_completed":workflows-len(errors),"concurrency":concurrency,"duration_seconds":round(duration,3),"throughput_per_second":round((workflows-len(errors))/duration,3),"errors":len(errors),"error_rate":round(len(errors)/workflows,6),"error_categories":categories,"orders":order_rows.count(),"trades":SimulatedTrade.objects.filter(order__subject_ref__in=subject_refs).count(),"reservations":SimulatedReservation.objects.filter(account__subject_ref__in=subject_refs).count(),"outbox_events":OutboxEvent.objects.filter(tenant_ref=str(organization.id),aggregate_id__in=order_ids).count(),"latency_ms":{key:{"p50":round(percentile(values,.5),3),"p95":round(percentile(values,.95),3),"p99":round(percentile(values,.99),3)} for key,values in timings.items()}}
        text=json.dumps(report,sort_keys=True); self.stdout.write(text)
        if options["output"]:
            from pathlib import Path
            Path(options["output"]).write_text(text+"\n")
        if errors: raise CommandError("LOAD_CERTIFICATION_ERRORS")
