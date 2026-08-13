from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.permissions import IsSreViewer,IsSecurityOperator,IsSreManager
from .models import KillSwitch
from .services import KillSwitchService
class KillSwitchListView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request):return Response({"kill_switches":[{"code":x.code,"state":x.state,"reason_code":x.reason_code,"version":x.version} for x in KillSwitch.objects.all()]})
class KillSwitchActivateView(APIView):
    permission_classes=(IsSecurityOperator,)
    def post(self,request,code):
        reason=request.data.get("reason_code")
        if not reason:return Response({"code":"REASON_CODE_REQUIRED"},status=400)
        try:x=KillSwitchService.activate(code=code,actor=request.user,reason_code=reason)
        except KillSwitch.DoesNotExist:return Response({"code":"NOT_FOUND"},status=404)
        return Response({"code":x.code,"state":x.state})
class KillSwitchRequestDeactivationView(APIView):
    permission_classes=(IsSreManager,)
    def post(self,request,code):
        reason=request.data.get("reason_code")
        if not reason:return Response({"code":"REASON_CODE_REQUIRED"},status=400)
        try:x=KillSwitchService.request_deactivation(code=code,actor=request.user,reason_code=reason)
        except KillSwitch.DoesNotExist:return Response({"code":"NOT_FOUND"},status=404)
        return Response({"request_id":x.id,"state":x.state},status=202)
class KillSwitchApproveDeactivationView(APIView):
    permission_classes=(IsSreManager,)
    def post(self,request,code):
        try:x=KillSwitchService.approve_deactivation(code=code,request_id=request.data.get("request_id"),actor=request.user)
        except ValueError:return Response({"code":"MAKER_CHECKER_REQUIRED"},status=409)
        except Exception:return Response({"code":"NOT_FOUND"},status=404)
        return Response({"code":x.code,"state":x.state})
