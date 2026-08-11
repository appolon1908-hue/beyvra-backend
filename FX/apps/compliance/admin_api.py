from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView
from .domain import RestrictionType
from .models import ComplianceCase, ComplianceOverride, ComplianceProfile
from .permissions import IsComplianceAnalyst, IsComplianceManager, IsComplianceViewer, authorized_organization_ids
from .services import add_restriction, append_case_event, approve_override, create_case, request_override

def safe_error(code,status=400): return Response({"error":{"code":code,"message":"The compliance action could not be completed."}},status=status)
def scoped_profile(request,account_id,role): return ComplianceProfile.objects.filter(pk=account_id,organization_id__in=authorized_organization_ids(request.user,role)).first()
def case_json(case): return {"case_id":str(case.pk),"account_id":str(case.account_id),"case_type":case.case_type,"status":case.status,"priority":case.priority,"reason_codes":case.reason_codes,"assigned_to":str(case.assigned_to_id) if case.assigned_to_id else None,"created_at":case.created_at,"updated_at":case.updated_at,"resolved_at":case.resolved_at,"resolution":case.resolution}

class CaseCollectionView(APIView):
    permission_classes=(IsComplianceViewer,)
    def get(self,request):
        orgs=authorized_organization_ids(request.user,"compliance_viewer")
        return Response({"results":[case_json(x) for x in ComplianceCase.objects.filter(account__organization_id__in=orgs).order_by("-created_at")[:100]]})
    def post(self,request):
        if not IsComplianceAnalyst().has_permission(request,self): return safe_error("INSUFFICIENT_COMPLIANCE_ROLE",403)
        profile=scoped_profile(request,request.data.get("account_id"),"compliance_analyst")
        if not profile: return safe_error("RESOURCE_NOT_FOUND",404)
        reasons=request.data.get("reason_codes",[])
        if not isinstance(reasons,list) or not reasons: return safe_error("REASON_REQUIRED")
        case=create_case(profile,str(request.data.get("case_type","MANUAL_REVIEW"))[:40],str(request.data.get("priority","NORMAL"))[:16],reasons,request.user)
        return Response(case_json(case),status=201)

class CaseEventView(APIView):
    permission_classes=(IsComplianceAnalyst,)
    def post(self,request,case_id):
        case=ComplianceCase.objects.filter(pk=case_id,account__organization_id__in=authorized_organization_ids(request.user,"compliance_analyst")).first()
        if not case:return safe_error("RESOURCE_NOT_FOUND",404)
        event_type=request.data.get("event_type","")
        if event_type in ("CASE_APPROVED","CASE_REJECTED","CASE_CLOSED") and not IsComplianceManager().has_permission(request,self): return safe_error("INSUFFICIENT_COMPLIANCE_ROLE",403)
        metadata={} if event_type=="CASE_NOTE_ADDED" else request.data.get("metadata",{})
        try:event=append_case_event(case.pk,event_type,request.user,metadata)
        except ValueError as exc:return safe_error(str(exc))
        return Response({"event_id":str(event.pk),"event_type":event.event_type,"created_at":event.created_at},status=201)

class RestrictionCollectionView(APIView):
    permission_classes=(IsComplianceAnalyst,)
    def post(self,request):
        profile=scoped_profile(request,request.data.get("account_id"),"compliance_analyst")
        if not profile:return safe_error("RESOURCE_NOT_FOUND",404)
        try:r_type=RestrictionType(request.data.get("restriction_type"))
        except ValueError:return safe_error("INVALID_RESTRICTION_TYPE")
        restriction=add_restriction(profile,r_type,str(request.data.get("reason_code","POLICY"))[:64],"MANUAL",request.user)
        return Response({"restriction_id":str(restriction.pk),"active":True},status=201)

class OverrideCollectionView(APIView):
    permission_classes=(IsComplianceAnalyst,)
    def post(self,request):
        profile=scoped_profile(request,request.data.get("account_id"),"compliance_analyst")
        if not profile:return safe_error("RESOURCE_NOT_FOUND",404)
        reason=str(request.data.get("reason","")).strip()
        if len(reason)<10:return safe_error("REASON_REQUIRED")
        try:override=request_override(profile,str(request.data.get("control","")),str(request.data.get("new_state","")),reason,request.user,parse_datetime(request.data.get("expires_at","")) if request.data.get("expires_at") else None)
        except ValueError as exc:return safe_error(str(exc))
        return Response({"override_id":str(override.pk),"status":"PENDING_SECOND_APPROVAL"},status=201)

class OverrideApprovalView(APIView):
    permission_classes=(IsComplianceManager,)
    def post(self,request,override_id):
        override=ComplianceOverride.objects.filter(pk=override_id,account__organization_id__in=authorized_organization_ids(request.user,"compliance_manager")).first()
        if not override:return safe_error("RESOURCE_NOT_FOUND",404)
        try:override=approve_override(override.pk,request.user)
        except ValueError as exc:return safe_error(str(exc),409)
        return Response({"override_id":str(override.pk),"status":"APPROVED","approved_at":override.approved_at})
