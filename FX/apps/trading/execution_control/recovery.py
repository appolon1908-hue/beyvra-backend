from django.db import transaction
from django.utils import timezone
from apps.foundation.services import enqueue_event
from apps.trading.models import UnknownExecutionOutcome

class ExecutionRecoveryService:
    @transaction.atomic
    def resolve_unknown(self,outcome,lookup):
        outcome=UnknownExecutionOutcome.objects.select_for_update().select_related("execution").get(pk=outcome.pk)
        if outcome.state=="RESOLVED": return outcome
        result=lookup(outcome.execution)
        outcome.lookup_attempts+=1; outcome.last_lookup_at=timezone.now()
        if not result:
            outcome.save(update_fields=("lookup_attempts","last_lookup_at")); return outcome
        outcome.state="RESOLVED"; outcome.resolved_at=timezone.now(); outcome.resolution_evidence_hash=result["evidence_hash"]; outcome.save()
        enqueue_event(aggregate_type="execution",aggregate_id=outcome.execution_id,event_type="execution.reconciled.v1",payload={"execution_id":str(outcome.execution_id),"resolved":True,"retry_allowed":False},tenant_ref=outcome.execution.order.tenant_ref)
        return outcome
