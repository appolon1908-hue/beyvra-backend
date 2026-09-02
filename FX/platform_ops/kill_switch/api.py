from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from django.db import transaction
from platform_ops.commands import VERSIONED_COMMAND_PARAMETERS, begin_command, command_context, complete_command
from platform_ops.permissions import IsSreViewer,IsSecurityOperator,IsSreManager
from .models import KillSwitch
from .services import KillSwitchService
class KillSwitchListView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request):return Response({"kill_switches":[{"code":x.code,"state":x.state,"reason_code":x.reason_code,"version":x.version} for x in KillSwitch.objects.all()]})
class KillSwitchActivateView(APIView):
    permission_classes=(IsSecurityOperator,)
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self,request,code):
        reason=request.data.get("reason_code")
        if not reason:return Response({"code":"REASON_CODE_REQUIRED"},status=400)
        command,error=command_context(request,require_version=True)
        if error:return error
        key,request_id,correlation_id,expected_version=command
        try:switch=KillSwitch.objects.select_for_update().get(code=code,scope_type="GLOBAL",scope_ref="")
        except KillSwitch.DoesNotExist:return Response({"code":"NOT_FOUND"},status=404)
        record_id,_,replay=begin_command(request,key=key,payload={"code":code,"action":"activate","reason_code":reason,"expected_version":expected_version})
        if replay:return replay
        if expected_version != str(switch.version):record_id.delete();return Response({"code":"VERSION_CONFLICT"},status=409)
        x=KillSwitchService.activate(code=code,actor=request.user,reason_code=reason,request_id=request_id,correlation_id=correlation_id)
        body=complete_command(record_id,status=200,body={"code":x.code,"state":x.state,"version":x.version},resource_type="kill_switch",resource_id=x.id);return Response(body)
class KillSwitchRequestDeactivationView(APIView):
    permission_classes=(IsSreManager,)
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self,request,code):
        reason=request.data.get("reason_code")
        if not reason:return Response({"code":"REASON_CODE_REQUIRED"},status=400)
        command,error=command_context(request,require_version=True)
        if error:return error
        key,request_id,correlation_id,expected_version=command
        try:switch=KillSwitch.objects.select_for_update().get(code=code,scope_type="GLOBAL",scope_ref="")
        except KillSwitch.DoesNotExist:return Response({"code":"NOT_FOUND"},status=404)
        record_id,_,replay=begin_command(request,key=key,payload={"code":code,"action":"request_deactivation","reason_code":reason,"expected_version":expected_version})
        if replay:return replay
        if expected_version != str(switch.version):record_id.delete();return Response({"code":"VERSION_CONFLICT"},status=409)
        x=KillSwitchService.request_deactivation(code=code,actor=request.user,reason_code=reason,request_id=request_id,correlation_id=correlation_id)
        body=complete_command(record_id,status=202,body={"request_id":x.id,"state":x.state},resource_type="kill_switch_deactivation",resource_id=x.id);return Response(body,status=202)
class KillSwitchApproveDeactivationView(APIView):
    permission_classes=(IsSreManager,)
    @extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self,request,code):
        command,error=command_context(request,require_version=True)
        if error:return error
        key,request_id,correlation_id,expected_version=command
        deactivation_request_id=request.data.get("request_id")
        record_id,_,replay=begin_command(request,key=key,payload={"code":code,"action":"approve_deactivation","deactivation_request_id":deactivation_request_id,"expected_version":expected_version})
        if replay:return replay
        try:switch=KillSwitch.objects.select_for_update().get(code=code,scope_type="GLOBAL",scope_ref="")
        except KillSwitch.DoesNotExist:record_id.delete();return Response({"code":"NOT_FOUND"},status=404)
        if expected_version != str(switch.version):record_id.delete();return Response({"code":"VERSION_CONFLICT"},status=409)
        try:x=KillSwitchService.approve_deactivation(code=code,request_id=deactivation_request_id,actor=request.user,audit_request_id=request_id,correlation_id=correlation_id)
        except ValueError:record_id.delete();return Response({"code":"MAKER_CHECKER_REQUIRED"},status=409)
        except Exception:record_id.delete();return Response({"code":"NOT_FOUND"},status=404)
        body=complete_command(record_id,status=200,body={"code":x.code,"state":x.state,"version":x.version},resource_type="kill_switch",resource_id=x.id);return Response(body)
