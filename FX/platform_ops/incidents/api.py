from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.audit import record
from platform_ops.permissions import IsSreViewer,IsIncidentCommander
from .models import OperationalIncident
from .services import IncidentService
def row(x):return {"id":x.id,"severity":x.severity,"category":x.category,"state":x.state,"summary":x.summary,"source":x.source,"opened_at":x.opened_at,"acknowledged_at":x.acknowledged_at,"resolved_at":x.resolved_at,"owner":x.owner,"release_id":x.release_id,"evidence_ref":x.evidence_ref}
class IncidentView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request,incident_id=None):
        if incident_id:
            try:return Response(row(OperationalIncident.objects.get(id=incident_id)))
            except OperationalIncident.DoesNotExist:return Response({"code":"NOT_FOUND"},status=404)
        return Response({"incidents":[row(x) for x in OperationalIncident.objects.order_by("-opened_at")[:200]]})
class IncidentTransitionView(APIView):
    permission_classes=(IsIncidentCommander,); state=None
    def post(self,request,incident_id):
        reason=request.data.get("reason_code")
        if not reason:return Response({"code":"REASON_CODE_REQUIRED"},status=400)
        try:x=IncidentService.transition(OperationalIncident.objects.get(id=incident_id),self.state)
        except OperationalIncident.DoesNotExist:return Response({"code":"NOT_FOUND"},status=404)
        except ValueError:return Response({"code":"INVALID_STATE_TRANSITION"},status=409)
        record(request=request,action=f"incident.{self.state.lower()}",resource_type="operational_incident",resource_id=x.id,reason_code=reason);return Response(row(x))
class IncidentAcknowledgeView(IncidentTransitionView):state="ACKNOWLEDGED"
class IncidentResolveView(IncidentTransitionView):state="RESOLVED"
