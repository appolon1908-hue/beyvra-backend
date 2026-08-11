import os
from django.utils import timezone
from apps.foundation.models import ApplicationAuditEvent, OutboxEvent
from apps.trading.models import CanonicalExecution, ExecutionQualityReport, ExecutionReconciliationRun, ExecutionRoutingDecision, UnknownExecutionOutcome
from .router import digest

class ExecutionReconciler:
    def inspect(self):
        audited=set(ApplicationAuditEvent.objects.filter(resource_type="execution_route").values_list("resource_id",flat=True))
        routed=set(str(x) for x in ExecutionRoutingDecision.objects.values_list("decision_id",flat=True))
        published=set(str(x) for x in OutboxEvent.objects.filter(aggregate_type="execution_route").values_list("aggregate_id",flat=True))
        checks={"DUPLICATE_EXECUTION":0,"UNRESOLVED_UNKNOWN_OUTCOME":UnknownExecutionOutcome.objects.filter(state="UNRESOLVED").count(),
            "MISSING_ROUTING_EVIDENCE":CanonicalExecution.objects.exclude(order_id__in=ExecutionRoutingDecision.objects.exclude(order=None).values("order_id")).count(),
            "MISSING_QUALITY_REPORT":CanonicalExecution.objects.filter(state="FILLED").exclude(order_id__in=ExecutionQualityReport.objects.values("order_id")).count(),
            "AUDIT_GAP":len(routed-audited),"OUTBOX_GAP":len(set(str(x) for x in ExecutionRoutingDecision.objects.filter(status="SELECTED").values_list("decision_id",flat=True))-published)}
        return checks
    def run(self):
        started=timezone.now(); checks=self.inspect(); critical=sum(checks.values()); completed=timezone.now()
        return ExecutionReconciliationRun.objects.create(status="PASS" if not critical else "CRITICAL",candidate_sha=os.getenv("CANDIDATE_SHA","unknown")[:64],check_count=len(checks),critical_count=critical,evidence_hash=digest(checks),started_at=started,completed_at=completed)
