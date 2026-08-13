from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from apps.compliance.models import AccountRestriction, ComplianceAuditEvent, ComplianceProfile, EligibilityDecision
from apps.compliance.metrics import reconciliation_violations, refresh_compliance_metrics
from apps.compliance.services import effective_profile_states

class Command(BaseCommand):
    help="Fail if persisted compliance eligibility contradicts authoritative state."
    def handle(self,*args,**kwargs):
        latest={}
        for decision in EligibilityDecision.objects.order_by("account_id","capability","-evaluated_at"):
            latest.setdefault((decision.account_id,decision.capability),decision)
        allowed=[decision for decision in latest.values() if decision.result=="ALLOWED"]
        effective={decision.account_id:effective_profile_states(decision.account) for decision in allowed}
        blocked=sum(1 for decision in allowed if effective[decision.account_id]["kyc_state"]!="APPROVED" or effective[decision.account_id]["aml_state"]!="CLEARED" or effective[decision.account_id]["sanctions_state"]!="CLEAR" or effective[decision.account_id]["jurisdiction_state"]!="SUPPORTED")
        restricted=sum(1 for decision in allowed if decision.capability=="TRADING" and decision.account.account_state in ("RESTRICTED","SUSPENDED","CLOSED"))
        now=timezone.now()
        restricted+=sum(1 for decision in allowed if decision.capability=="TRADING" and AccountRestriction.objects.filter(account=decision.account,active=True,restriction_type__in=("TRADING_DISABLED","ACCOUNT_READ_ONLY")).filter(Q(expires_at__isnull=True)|Q(expires_at__gt=now)).exists())
        audited_ids={str(event.state_after.get("decision_id")) for event in ComplianceAuditEvent.objects.filter(event_type="ELIGIBILITY_DECISION") if event.state_after.get("decision_id")}
        missing=sum(1 for decision in EligibilityDecision.objects.all() if str(decision.pk) not in audited_ids)
        refresh_compliance_metrics(); reconciliation_violations.labels(kind="blocked_allowed").set(blocked); reconciliation_violations.labels(kind="restricted_allowed").set(restricted); reconciliation_violations.labels(kind="missing_audit").set(missing)
        self.stdout.write(f"approved eligibility with blocked compliance = {blocked}\nrestricted account allowed trade = {restricted}\nmissing compliance audit events = {missing}")
        if blocked or restricted or missing: raise SystemExit(1)
