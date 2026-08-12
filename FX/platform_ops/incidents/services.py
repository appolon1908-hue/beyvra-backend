from django.utils import timezone
from .models import OperationalIncident
class IncidentService:
    @staticmethod
    def open_or_get(**values):
        active=("OPEN","ACKNOWLEDGED","INVESTIGATING","MITIGATED")
        existing=OperationalIncident.objects.filter(deduplication_key=values["deduplication_key"],state__in=active).first()
        return (existing,False) if existing else (OperationalIncident.objects.create(**values),True)
    @staticmethod
    def transition(incident,state):
        allowed={"OPEN":{"ACKNOWLEDGED"},"ACKNOWLEDGED":{"INVESTIGATING","RESOLVED"},"INVESTIGATING":{"MITIGATED","RESOLVED"},"MITIGATED":{"RESOLVED"},"RESOLVED":{"POSTMORTEM_PENDING","CLOSED"},"POSTMORTEM_PENDING":{"CLOSED"}}
        if state not in allowed.get(incident.state,set()):raise ValueError("INVALID_INCIDENT_TRANSITION")
        incident.state=state
        if state=="ACKNOWLEDGED":incident.acknowledged_at=timezone.now()
        if state=="RESOLVED":incident.resolved_at=timezone.now()
        incident.save();return incident
