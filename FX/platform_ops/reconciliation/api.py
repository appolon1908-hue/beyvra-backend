from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema
from django.db import transaction
from platform_ops.commands import COMMAND_PARAMETERS, begin_command, command_context, complete_command
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
    @extend_schema(parameters=COMMAND_PARAMETERS)
    @transaction.atomic
    def post(self,request):
        reason=request.data.get("reason_code")
        if not reason:return Response({"code":"REASON_CODE_REQUIRED"},status=400)
        if not settings.RELEASE_SHA:return Response({"code":"CANDIDATE_IDENTITY_UNAVAILABLE"},status=503)
        command,error=command_context(request)
        if error:return error
        key,request_id,correlation_id,_=command
        record_id,_,replay=begin_command(request,key=key,payload={"candidate_sha":settings.RELEASE_SHA,"policy_version":"v1","reason_code":reason})
        if replay:return replay
        # The control plane does not infer domain invariants from an empty result.
        # Until every authoritative adapter supplies evidence, persist an honest
        # incomplete run and fail the operator request closed.
        x=record_run(candidate_sha=settings.RELEASE_SHA,policy_version="v1",results=None)
        record(request=request,action="reconciliation.incomplete",resource_type="full_stack_reconciliation",resource_id=x.id,reason_code=reason,request_id=request_id,correlation_id=correlation_id)
        body={"code":"RECONCILIATION_SOURCES_UNAVAILABLE","reconciliation":row(x)}
        body=complete_command(record_id,status=503,body=body,resource_type="full_stack_reconciliation",resource_id=x.id)
        return Response(body,status=503)
