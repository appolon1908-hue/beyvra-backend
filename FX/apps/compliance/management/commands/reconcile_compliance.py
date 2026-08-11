from django.core.management.base import BaseCommand
from apps.compliance.models import ComplianceAuditEvent, ComplianceProfile, EligibilityDecision

class Command(BaseCommand):
    help="Fail if persisted compliance eligibility contradicts authoritative state."
    def handle(self,*args,**kwargs):
        blocked=EligibilityDecision.objects.filter(result="ALLOWED",account__aml_state="BLOCKED").count()+EligibilityDecision.objects.filter(result="ALLOWED",account__sanctions_state="CONFIRMED_MATCH").count()
        restricted=EligibilityDecision.objects.filter(result="ALLOWED",capability="TRADING",account__account_state__in=("RESTRICTED","SUSPENDED","CLOSED")).count()
        missing=sum(1 for p in ComplianceProfile.objects.all() if p.eligibility_decisions.exists() and not ComplianceAuditEvent.objects.filter(account=p,event_type="ELIGIBILITY_DECISION").exists())
        self.stdout.write(f"approved eligibility with blocked compliance = {blocked}\nrestricted account allowed trade = {restricted}\nmissing compliance audit events = {missing}")
        if blocked or restricted or missing: raise SystemExit(1)
