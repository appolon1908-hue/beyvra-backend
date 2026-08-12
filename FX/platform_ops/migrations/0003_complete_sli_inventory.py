from datetime import timedelta

from django.db import migrations
from django.utils import timezone


SLIS = (
    # Targets are provisional staging engineering policies, never contractual
    # production commitments. Units match their PromQL results.
    ("api_latency_p50", "LATENCY", "histogram_quantile(0.50,sum(rate(beyvra_http_request_duration_seconds_bucket[5m])) by (le))", "0.250000", "<="),
    ("api_latency_p99", "LATENCY", "histogram_quantile(0.99,sum(rate(beyvra_http_request_duration_seconds_bucket[5m])) by (le))", "1.000000", "<="),
    ("api_error_rate", "ERROR_RATE", "sum(rate(beyvra_http_requests_total{status_class=~\"5..\"}[5m])) / sum(rate(beyvra_http_requests_total[5m]))", "0.010000", "<="),
    ("jetstream_pending", "QUEUE_DEPTH", "max(beyvra_consumer_lag{dependency=\"jetstream\"})", "1000.000000", "<="),
    ("worker_job_latency", "LATENCY", "max(beyvra_worker_job_latency_seconds)", "5.000000", "<="),
    ("backup_rpo", "RECOVERY_TIME", "time() - max(beyvra_backup_last_success_timestamp_seconds)", "86400.000000", "<="),
)


def seed(apps, schema_editor):
    Sli = apps.get_model("platform_ops", "SliDefinition")
    Slo = apps.get_model("platform_ops", "SloDefinition")
    for code, metric_type, query, target, comparison in SLIS:
        sli, _ = Sli.objects.get_or_create(
            code=code,
            defaults={
                "service_code": "web-api",
                "metric_type": metric_type,
                "query_definition": query,
                "aggregation": "PROMQL",
                "window": timedelta(minutes=5),
                "status": "ACTIVE",
                "version": "v1",
            },
        )
        Slo.objects.get_or_create(
            code=f"{code}_objective",
            defaults={
                "sli": sli,
                "target": target,
                "comparison": comparison,
                "window": timedelta(days=30),
                "error_budget_policy": {
                    "short_window": "5m",
                    "long_window": "1h",
                    "thresholds": "POLICY_REQUIRED",
                },
                "status": "ACTIVE",
                "version": "v1",
                "effective_from": timezone.now(),
            },
        )


def unseed(apps, schema_editor):
    Sli = apps.get_model("platform_ops", "SliDefinition")
    Slo = apps.get_model("platform_ops", "SloDefinition")
    codes = [row[0] for row in SLIS]
    Slo.objects.filter(sli__code__in=codes).delete()
    Sli.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [("platform_ops", "0002_seed_safe_control_plane")]
    operations = [migrations.RunPython(seed, unseed)]
