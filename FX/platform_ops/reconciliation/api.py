from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from platform_ops.audit import record
from platform_ops.permissions import IsSreViewer,IsSreOperator
from .full_stack import record_run
from .models import FullStackReconciliationRun
def row(x):return {"run_id":x.id,"state":x.state,"checks":x.checks,"violations":x.violations,"candidate_sha":x.candidate_sha,"policy_version":x.policy_version,"started_at":x.started_at,"completed_at":x.completed_at}
class ReconciliationView(APIView):
    permission_classes=(IsSreViewer,)
    def get(self,request):
        x=FullStackReconciliationRun.objects.order_by("-started_at").first();return Response({"reconciliation":row(x) if x else None})
class ReconciliationRunView(APIView):
    permission_classes=(IsSreOperator,)
    def post(self,request):
        reason=request.data.get("reason_code")
        if not reason:return Response({"code":"REASON_CODE_REQUIRED"},status=400)
        if not settings.RELEASE_SHA:return Response({"code":"CANDIDATE_IDENTITY_UNAVAILABLE"},status=503)
        x=record_run(candidate_sha=settings.RELEASE_SHA,policy_version="v1",results={})
        record(request=request,action="reconciliation.run",resource_type="full_stack_reconciliation",resource_id=x.id,reason_code=reason);return Response(row(x),status=201)
