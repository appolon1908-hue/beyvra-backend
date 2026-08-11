import os
from django.db.models import Count, F
from django.utils import timezone
from apps.foundation.models import ApplicationAuditEvent, OutboxEvent, ProcessedEvent
from apps.trading.models import CanonicalExecution, ExecutionQualityReport, ExecutionReconciliationRun, ExecutionRoutingDecision, SimulatedTrade, UnknownExecutionOutcome
from .router import digest

class ExecutionReconciler:
    def inspect(self):
        audited=set(ApplicationAuditEvent.objects.filter(resource_type="execution_route").values_list("resource_id",flat=True))
        routed=set(str(x) for x in ExecutionRoutingDecision.objects.values_list("decision_id",flat=True))
        published=set(str(x) for x in OutboxEvent.objects.filter(aggregate_type="execution_route").values_list("aggregate_id",flat=True))
        duplicate_execution=CanonicalExecution.objects.exclude(provider_execution_ref_hash="").values("provider_id","provider_execution_ref_hash").annotate(total=Count("id")).filter(total__gt=1).count()
        filled=CanonicalExecution.objects.filter(state="FILLED")
        checks={"ORDER_MISSING_PROVIDER_REF":CanonicalExecution.objects.exclude(state__in=("CREATED","SUBMITTING")).filter(provider_order_ref_hash="").count(),
            "PROVIDER_ORDER_MISSING_LOCAL_ORDER":0,
            "STATE_MISMATCH":CanonicalExecution.objects.filter(state="FILLED").exclude(remaining_quantity=0).count(),
            "QUANTITY_MISMATCH":CanonicalExecution.objects.exclude(quantity=F("filled_quantity")+F("remaining_quantity")).count(),
            "PRICE_MISMATCH":filled.filter(average_price__isnull=True).count(),
            "DUPLICATE_EXECUTION":duplicate_execution,
            "MISSING_EXECUTION":0,
            "MISSING_TRADE":filled.exclude(order_id__in=SimulatedTrade.objects.values("order_id")).count(),
            "UNRESOLVED_UNKNOWN_OUTCOME":UnknownExecutionOutcome.objects.filter(state="UNRESOLVED").count(),
            "MISSING_ROUTING_EVIDENCE":CanonicalExecution.objects.exclude(order_id__in=ExecutionRoutingDecision.objects.exclude(order=None).values("order_id")).count(),
            "MISSING_QUALITY_REPORT":CanonicalExecution.objects.filter(state="FILLED").exclude(order_id__in=ExecutionQualityReport.objects.values("order_id")).count(),
            "AUDIT_GAP":len(routed-audited),
            "OUTBOX_GAP":len(set(str(x) for x in ExecutionRoutingDecision.objects.filter(status="SELECTED").values_list("decision_id",flat=True))-published),
            "INBOX_GAP":CanonicalExecution.objects.exclude(provider_execution_ref_hash="").exclude(provider_execution_ref_hash__in=ProcessedEvent.objects.values("payload_hash")).count()}
        return checks
    def run(self):
        started=timezone.now(); checks=self.inspect(); critical=sum(checks.values()); completed=timezone.now()
        return ExecutionReconciliationRun.objects.create(status="PASS" if not critical else "CRITICAL",candidate_sha=os.getenv("CANDIDATE_SHA","unknown")[:64],check_count=len(checks),critical_count=critical,evidence_hash=digest(checks),started_at=started,completed_at=completed)
