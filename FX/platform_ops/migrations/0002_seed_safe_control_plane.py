from datetime import timedelta
from django.db import migrations
from django.utils import timezone

SERVICES=(
 ("web-api","API","TIER_0"),("outbox-publisher","WORKER","TIER_0"),("execution-consumer","CONSUMER","TIER_1"),("post-trade-consumer","CONSUMER","TIER_1"),
 ("valuation-worker","WORKER","TIER_1"),("treasury-worker","WORKER","TIER_1"),("regulatory-records-worker","WORKER","TIER_1"),("realtime-bridge","REALTIME","TIER_1"),
 ("redis","CACHE","TIER_1"),("nats","MESSAGE_BROKER","TIER_1"),("jetstream","MESSAGE_BROKER","TIER_1"),("postgresql","DATABASE","TIER_0"))
FLAGS=("REAL_TRADING_ENABLED","EXTERNAL_EXECUTION_ENABLED","REAL_SETTLEMENT_ENABLED","REAL_MONEY_ENABLED","REAL_WITHDRAWALS_ENABLED","REAL_TREASURY_TRANSFERS_ENABLED","LIVE_BROKER_ROUTING_ENABLED","FIX_LIVE_SESSION_ENABLED")
SWITCHES=("GLOBAL_PLATFORM_HALT","TRADING_HALT","EXECUTION_HALT","WITHDRAWAL_HALT","SETTLEMENT_HALT","TREASURY_HALT","MARKET_DATA_PROVIDER_HALT","NEWS_PROVIDER_HALT","DEVELOPER_API_HALT","REALTIME_HALT")
SLIS=(("api_availability","AVAILABILITY","sum(rate(beyvra_http_requests_total{status_class!~\"5..\"}[5m])) / sum(rate(beyvra_http_requests_total[5m]))"),("api_latency_p95","LATENCY","histogram_quantile(0.95,sum(rate(beyvra_http_request_duration_seconds_bucket[5m])) by (le))"),("ws_availability","AVAILABILITY","avg_over_time(up{service=\"realtime\"}[5m])"),("ws_delivery_lag","LATENCY","histogram_quantile(0.95,sum(rate(beyvra_ws_delivery_lag_seconds_bucket[5m])) by (le))"),("market_data_freshness","DATA_FRESHNESS","max(beyvra_market_data_age_seconds)"),("consumer_lag","CONSUMER_LAG","max(beyvra_consumer_lag)"),("outbox_age","DURABILITY","max(beyvra_outbox_oldest_age_seconds)"),("db_saturation","QUEUE_DEPTH","max(beyvra_db_pool_utilization)"),("restore_rto","RECOVERY_TIME","beyvra_restore_duration_seconds"))

def seed(apps,schema_editor):
    Service=apps.get_model("platform_ops","ServiceDefinition");Dependency=apps.get_model("platform_ops","ServiceDependency");Flag=apps.get_model("platform_ops","FeatureFlagDefinition");Switch=apps.get_model("platform_ops","KillSwitch");Sli=apps.get_model("platform_ops","SliDefinition");Slo=apps.get_model("platform_ops","SloDefinition")
    for code,kind,tier in SERVICES:Service.objects.get_or_create(code=code,defaults={"name":code.replace("-"," ").title(),"service_type":kind,"criticality":tier,"owner":"platform-sre","runtime_type":"PROCESS" if kind not in {"DATABASE","CACHE","MESSAGE_BROKER"} else "DEPENDENCY","health_check_type":"BOUNDED","readiness_policy":{},"status":"ACTIVE"})
    web=Service.objects.get(code="web-api")
    for code,kind in (("postgresql","DATABASE"),("redis","CACHE"),("nats","MESSAGE_BROKER"),("jetstream","MESSAGE_BROKER")):Dependency.objects.get_or_create(service=web,dependency_code=code,defaults={"dependency_type":kind,"required_for_liveness":False,"required_for_readiness":code in {"postgresql","redis"},"required_for_writes":True,"required_for_simulation":code in {"postgresql","redis"},"failure_mode":"FAIL_CLOSED","timeout_ms":1000})
    for code in FLAGS:Flag.objects.get_or_create(code=code,defaults={"owner":"platform-security","risk_class":"HIGH","default_state":False,"fail_closed_state":False,"environment_constraints":{"production":"external_approval_required"},"status":"ACTIVE","version":"v1"})
    for code in SWITCHES:Switch.objects.get_or_create(code=code,scope_type="GLOBAL",scope_ref="",defaults={"state":"INACTIVE","version":1})
    now=timezone.now()
    for code,kind,query in SLIS:
        sli,_=Sli.objects.get_or_create(code=code,defaults={"service_code":"web-api","metric_type":kind,"query_definition":query,"aggregation":"PROMQL","window":timedelta(minutes=5),"status":"ACTIVE","version":"v1"})
        Slo.objects.get_or_create(code=f"{code}_objective",defaults={"sli":sli,"target":"0.990000","comparison":">=","window":timedelta(days=30),"error_budget_policy":{"short_window":"5m","long_window":"1h","thresholds":"POLICY_REQUIRED"},"status":"ACTIVE","version":"v1","effective_from":now})

class Migration(migrations.Migration):
    dependencies=[("platform_ops","0001_initial")]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop)]
