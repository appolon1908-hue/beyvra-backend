from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from django.db import transaction
from platform_ops.commands import VERSIONED_COMMAND_PARAMETERS, begin_command, command_context, complete_command
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
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self,request,incident_id):
        reason=request.data.get("reason_code")
        if not reason:return Response({"code":"REASON_CODE_REQUIRED"},status=400)
        command,error=command_context(request,require_version=True)
        if error:return error
        key,request_id,correlation_id,expected_version=command
        try:x=OperationalIncident.objects.select_for_update().get(id=incident_id)
        except OperationalIncident.DoesNotExist:return Response({"code":"NOT_FOUND"},status=404)
        record_id,_,replay=begin_command(request,key=key,payload={"incident_id":str(incident_id),"state":self.state,"reason_code":reason,"expected_version":expected_version})
        if replay:return replay
        if expected_version != x.state:
            record_id.delete();return Response({"code":"VERSION_CONFLICT"},status=409)
        try:x=IncidentService.transition(x,self.state)
        except ValueError:record_id.delete();return Response({"code":"INVALID_STATE_TRANSITION"},status=409)
        record(request=request,action=f"incident.{self.state.lower()}",resource_type="operational_incident",resource_id=x.id,reason_code=reason,request_id=request_id,correlation_id=correlation_id)
        body=complete_command(record_id,status=200,body=row(x),resource_type="operational_incident",resource_id=x.id);return Response(body)
class IncidentAcknowledgeView(IncidentTransitionView):state="ACKNOWLEDGED"
class IncidentResolveView(IncidentTransitionView):state="RESOLVED"
