import json
import math
import time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from integrations.models import Organization
from apps.institutional.models import InstitutionalAccount, InstitutionalPosition, InstitutionalSubaccount
from apps.institutional.services import InstitutionAggregationService, InstitutionalAccountReconciler, InstitutionalRiskService


def percentile(values, percentile_value):
    values = sorted(values)
    return values[min(len(values) - 1, math.ceil(len(values) * percentile_value) - 1)]


class Command(BaseCommand):
    help = "Run bounded, rollback-only institutional hierarchy and aggregation load certification."

    def add_arguments(self, parser):
        parser.add_argument("--institutions", type=int, default=100)
        parser.add_argument("--subaccounts", type=int, default=1000)

    def handle(self, *args, **options):
        institution_count = min(max(options["institutions"], 1), 100)
        subaccount_count = min(max(options["subaccounts"], institution_count), 10_000)
        now = timezone.now()
        with transaction.atomic():
            tenant = Organization.objects.create(name="Synthetic institutional load certification")
            institutions = [InstitutionalAccount(tenant=tenant, institution_code=f"LOAD-{index:03d}", display_name=f"Synthetic {index}", account_type="INTERNAL_TEST", status="ACTIVE", base_currency="USD", effective_from=now) for index in range(institution_count)]
            InstitutionalAccount.objects.bulk_create(institutions)
            institutions = list(InstitutionalAccount.objects.filter(tenant=tenant).order_by("institution_code"))
            subaccounts = [InstitutionalSubaccount(institution=institutions[index % institution_count], tenant=tenant, code=f"SUB-{index:05d}", display_name=f"Synthetic subaccount {index}", subaccount_type="TEST", base_currency="USD", status="ACTIVE", allocation_eligible=True, effective_from=now) for index in range(subaccount_count)]
            InstitutionalSubaccount.objects.bulk_create(subaccounts)
            sample = institutions[0]
            sample_subaccounts = list(sample.subaccounts.order_by("code")[:100])
            InstitutionalPosition.objects.bulk_create([InstitutionalPosition(tenant=tenant, institution=sample, subaccount=row, instrument_id=f"SYNTH-{index % 10}", quantity=Decimal(index + 1), as_of=now) for index, row in enumerate(sample_subaccounts)])

            hierarchy_times, list_times, position_times, risk_times, reconciliation_times = [], [], [], [], []
            for _ in range(20):
                started = time.perf_counter(); list(sample.subaccounts.values("id", "parent_subaccount_id")); hierarchy_times.append((time.perf_counter() - started) * 1000)
                started = time.perf_counter(); list(InstitutionalSubaccount.objects.filter(tenant=tenant).order_by("id")[:100]); list_times.append((time.perf_counter() - started) * 1000)
                started = time.perf_counter(); InstitutionAggregationService.positions(institution=sample); position_times.append((time.perf_counter() - started) * 1000)
                started = time.perf_counter(); InstitutionalRiskService.evaluate(institution=sample); risk_times.append((time.perf_counter() - started) * 1000)
                started = time.perf_counter(); InstitutionalAccountReconciler.run(institution=sample); reconciliation_times.append((time.perf_counter() - started) * 1000)
            report = {
                "institutions": institution_count, "subaccounts": subaccount_count,
                "institution_hierarchy_p95_ms": round(percentile(hierarchy_times, .95), 3),
                "subaccount_list_p95_ms": round(percentile(list_times, .95), 3),
                "position_aggregation_p95_ms": round(percentile(position_times, .95), 3),
                "risk_aggregation_p95_ms": round(percentile(risk_times, .95), 3),
                "reconciliation_p95_ms": round(percentile(reconciliation_times, .95), 3),
                "result": "PASS",
            }
            transaction.set_rollback(True)
        self.stdout.write(json.dumps(report, sort_keys=True))
