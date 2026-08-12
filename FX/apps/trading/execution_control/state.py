from django.db import transaction
from django.utils import timezone
from apps.trading.models import CanonicalExecution

TRANSITIONS={"CREATED":{"SUBMITTING","REJECTED"},"SUBMITTING":{"SUBMITTED","UNKNOWN","REJECTED"},"SUBMITTED":{"ACKNOWLEDGED","UNKNOWN","REJECTED"},
"ACKNOWLEDGED":{"WORKING","PARTIALLY_FILLED","FILLED","CANCEL_PENDING","REJECTED"},"WORKING":{"PARTIALLY_FILLED","FILLED","CANCEL_PENDING","CANCELLED","EXPIRED"},
"PARTIALLY_FILLED":{"PARTIALLY_FILLED","FILLED","CANCEL_PENDING","CANCELLED"},"CANCEL_PENDING":{"CANCELLED","PARTIALLY_FILLED","FILLED"},"UNKNOWN":{"SUBMITTED","ACKNOWLEDGED","WORKING","PARTIALLY_FILLED","FILLED","CANCELLED","REJECTED"}}

class ExecutionStateAuthority:
    @transaction.atomic
    def transition(self,execution,new_state,**updates):
        execution=CanonicalExecution.objects.select_for_update().get(pk=execution.pk)
        if new_state not in TRANSITIONS.get(execution.state,set()): raise ValueError("INVALID_EXECUTION_STATE_TRANSITION")
        for key,value in updates.items(): setattr(execution,key,value)
        execution.state=new_state; execution.version+=1
        if new_state in {"FILLED","CANCELLED","REJECTED","EXPIRED"}: execution.completed_at=timezone.now()
        execution.save(); return execution
