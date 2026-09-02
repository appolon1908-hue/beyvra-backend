import uuid
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import IdempotencyConflict, begin_idempotent_request, complete_idempotent_request
from .domain import ReasonCode, RestrictionType
from .models import ComplianceCase, ComplianceOverride, ComplianceProfile
from .permissions import IsComplianceAnalyst, IsComplianceManager, IsComplianceViewer, authorized_organization_ids
from .services import add_restriction, append_case_event, approve_override, create_case, request_override

def safe_error(code,status=400): return Response({"error":{"code":code,"message":"The compliance action could not be completed."}},status=status)
def parse_expiration(value):
    parsed=parse_datetime(value) if value else None
    return parsed if parsed and not timezone.is_naive(parsed) else None
def scoped_profile(request,account_id,role): return ComplianceProfile.objects.filter(pk=account_id,organization_id__in=authorized_organization_ids(request.user,role)).first()
def _iso(value): return value.isoformat() if value else None
def case_json(case): return {"case_id":str(case.pk),"account_id":str(case.account_id),"case_type":case.case_type,"status":case.status,"priority":case.priority,"reason_codes":case.reason_codes,"assigned_to":str(case.assigned_to_id) if case.assigned_to_id else None,"created_at":_iso(case.created_at),"updated_at":_iso(case.updated_at),"version":_iso(case.updated_at),"resolved_at":_iso(case.resolved_at),"resolution":case.resolution}

IDEMPOTENCY_PARAMETERS=[OpenApiParameter("Idempotency-Key",str,OpenApiParameter.HEADER,required=True),OpenApiParameter("X-Request-ID",str,OpenApiParameter.HEADER,required=True)]
VERSIONED_PARAMETERS=[*IDEMPOTENCY_PARAMETERS,OpenApiParameter("If-Match",str,OpenApiParameter.HEADER,required=True,description="Resource version returned by the API.")]

def _headers(request,versioned=False):
    key=request.headers.get("Idempotency-Key","")
    request_id=request.headers.get("X-Request-ID","")
    version=request.headers.get("If-Match","") if versioned else None
    if not key or not request_id or (versioned and not version): return None,None,None
    return key,version,request_id[:128]

def _begin(request,tenant,endpoint,key,semantic):
    return begin_idempotent_request(key=key,tenant_ref=tenant,actor_ref=request.user.pk,endpoint=endpoint,method="POST",request_data=semantic)

def _replay(record,fresh):
    return None if fresh or record.response_body is None else Response(record.response_body,status=record.response_status)

def _audit(request,request_id,action,resource_type,resource_id,reason="",context=None):
    raw=str(getattr(request,"correlation_id","") or uuid.uuid4())
    try:correlation=uuid.UUID(raw)
    except ValueError:correlation=uuid.uuid5(uuid.NAMESPACE_URL,raw)
    return ApplicationAuditEvent.objects.create(actor_ref=str(request.user.pk),action=action,resource_type=resource_type,resource_id=str(resource_id),request_id=request_id,correlation_id=correlation,context=context or {},reason=reason[:255],occurred_at=timezone.now())

class CaseCollectionView(APIView):
    permission_classes=(IsComplianceViewer,)
    def get(self,request):
        orgs=authorized_organization_ids(request.user,"compliance_viewer")
        return Response({"results":[case_json(x) for x in ComplianceCase.objects.filter(account__organization_id__in=orgs).order_by("-created_at")[:100]]})
    @extend_schema(parameters=IDEMPOTENCY_PARAMETERS)
    def post(self,request):
        if not IsComplianceAnalyst().has_permission(request,self): return safe_error("INSUFFICIENT_COMPLIANCE_ROLE",403)
        profile=scoped_profile(request,request.data.get("account_id"),"compliance_analyst")
        if not profile: return safe_error("RESOURCE_NOT_FOUND",404)
        key,_,request_id=_headers(request)
        if not key:return safe_error("IDEMPOTENCY_KEY_REQUIRED",422)
        reasons=request.data.get("reason_codes",[])
        if not isinstance(reasons,list) or not reasons: return safe_error("REASON_REQUIRED")
        try:reasons=[ReasonCode(value).value for value in reasons]
        except ValueError:return safe_error("INVALID_REASON_CODE")
        case_type=str(request.data.get("case_type","MANUAL_REVIEW"))[:40];priority=str(request.data.get("priority","NORMAL"))[:16]
        try:
            with transaction.atomic():
                record,fresh=_begin(request,profile.organization_id,"/api/v1/admin/compliance/cases",key,{"account_id":str(profile.pk),"case_type":case_type,"priority":priority,"reason_codes":reasons})
                if replay:=_replay(record,fresh):return replay
                case=create_case(profile,case_type,priority,reasons,request.user);body=case_json(case)
                _audit(request,request_id,"compliance.case.created","compliance_case",case.pk,context={"organization_id":str(profile.organization_id)})
                complete_idempotent_request(record,status=201,body=body,resource_type="compliance_case",resource_id=case.pk)
                return Response(body,status=201)
        except IdempotencyConflict:return safe_error("IDEMPOTENCY_CONFLICT",409)

class CaseEventView(APIView):
    permission_classes=(IsComplianceAnalyst,)
    @extend_schema(parameters=VERSIONED_PARAMETERS)
    def post(self,request,case_id):
        case=ComplianceCase.objects.filter(pk=case_id,account__organization_id__in=authorized_organization_ids(request.user,"compliance_analyst")).first()
        if not case:return safe_error("RESOURCE_NOT_FOUND",404)
        event_type=request.data.get("event_type","")
        if event_type in ("CASE_APPROVED","CASE_REJECTED","CASE_CLOSED") and not IsComplianceManager().has_permission(request,self): return safe_error("INSUFFICIENT_COMPLIANCE_ROLE",403)
        key,version,request_id=_headers(request,True)
        if not key:return safe_error("COMMAND_HEADERS_REQUIRED",422)
        metadata=request.data.get("metadata",{})
        try:
            with transaction.atomic():
                case=ComplianceCase.objects.select_for_update().get(pk=case.pk)
                record,fresh=_begin(request,case.account.organization_id,f"/api/v1/admin/compliance/cases/{case.pk}/events",key,{"case_id":str(case.pk),"event_type":event_type,"metadata":metadata,"expected_version":version})
                if replay:=_replay(record,fresh):return replay
                if case.updated_at.isoformat()!=version:raise ValueError("VERSION_CONFLICT")
                event=append_case_event(case.pk,event_type,request.user,metadata);case.refresh_from_db()
                body={"event_id":str(event.pk),"event_type":event.event_type,"created_at":_iso(event.created_at),"case_version":_iso(case.updated_at)}
                _audit(request,request_id,f"compliance.case.{event_type.lower()}","compliance_case",case.pk,context={"event_id":str(event.pk)})
                complete_idempotent_request(record,status=201,body=body,resource_type="compliance_case_event",resource_id=event.pk)
                return Response(body,status=201)
        except IdempotencyConflict:return safe_error("IDEMPOTENCY_CONFLICT",409)
        except ValueError as exc:return safe_error(str(exc),409 if str(exc)=="VERSION_CONFLICT" else 400)

class RestrictionCollectionView(APIView):
    permission_classes=(IsComplianceAnalyst,)
    @extend_schema(parameters=VERSIONED_PARAMETERS)
    def post(self,request):
        profile=scoped_profile(request,request.data.get("account_id"),"compliance_analyst")
        if not profile:return safe_error("RESOURCE_NOT_FOUND",404)
        key,version,request_id=_headers(request,True)
        if not key:return safe_error("COMMAND_HEADERS_REQUIRED",422)
        try:r_type=RestrictionType(request.data.get("restriction_type"))
        except ValueError:return safe_error("INVALID_RESTRICTION_TYPE")
        expires_at=parse_expiration(request.data.get("expires_at",""))
        if request.data.get("expires_at") and not expires_at:return safe_error("INVALID_EXPIRATION")
        reason_code=str(request.data.get("reason_code",""))[:64]
        try:
            with transaction.atomic():
                profile=ComplianceProfile.objects.select_for_update().get(pk=profile.pk)
                record,fresh=_begin(request,profile.organization_id,"/api/v1/admin/compliance/restrictions",key,{"account_id":str(profile.pk),"restriction_type":r_type.value,"reason_code":reason_code,"expires_at":_iso(expires_at),"expected_version":version})
                if replay:=_replay(record,fresh):return replay
                if str(profile.version)!=version:raise ValueError("VERSION_CONFLICT")
                restriction=add_restriction(profile,r_type,reason_code,"MANUAL",request.user,expires_at=expires_at);profile.refresh_from_db()
                body={"restriction_id":str(restriction.pk),"active":True,"profile_version":str(profile.version)}
                _audit(request,request_id,"compliance.restriction.added","account_restriction",restriction.pk,reason=reason_code,context={"account_id":str(profile.pk),"profile_version":profile.version})
                complete_idempotent_request(record,status=201,body=body,resource_type="account_restriction",resource_id=restriction.pk)
                return Response(body,status=201)
        except IdempotencyConflict:return safe_error("IDEMPOTENCY_CONFLICT",409)
        except ValueError as exc:return safe_error(str(exc),409 if str(exc)=="VERSION_CONFLICT" else 400)

class OverrideCollectionView(APIView):
    permission_classes=(IsComplianceAnalyst,)
    @extend_schema(parameters=VERSIONED_PARAMETERS)
    def post(self,request):
        profile=scoped_profile(request,request.data.get("account_id"),"compliance_analyst")
        if not profile:return safe_error("RESOURCE_NOT_FOUND",404)
        key,version,request_id=_headers(request,True)
        if not key:return safe_error("COMMAND_HEADERS_REQUIRED",422)
        reason=str(request.data.get("reason","")).strip()
        if len(reason)<10:return safe_error("REASON_REQUIRED")
        expires_at=parse_expiration(request.data.get("expires_at",""))
        if request.data.get("expires_at") and not expires_at:return safe_error("INVALID_EXPIRATION")
        control=str(request.data.get("control",""));new_state=str(request.data.get("new_state",""));evidence_ref=str(request.data.get("evidence_ref",""))[:255]
        try:
            with transaction.atomic():
                profile=ComplianceProfile.objects.select_for_update().get(pk=profile.pk)
                record,fresh=_begin(request,profile.organization_id,"/api/v1/admin/compliance/overrides",key,{"account_id":str(profile.pk),"control":control,"new_state":new_state,"reason":reason,"expires_at":_iso(expires_at),"evidence_ref":evidence_ref,"expected_version":version})
                if replay:=_replay(record,fresh):return replay
                if str(profile.version)!=version:raise ValueError("VERSION_CONFLICT")
                override=request_override(profile,control,new_state,reason,request.user,expires_at,evidence_ref)
                body={"override_id":str(override.pk),"status":"PENDING_SECOND_APPROVAL","version":_iso(override.requested_at)}
                _audit(request,request_id,"compliance.override.requested","compliance_override",override.pk,reason=reason,context={"account_id":str(profile.pk),"control":control})
                complete_idempotent_request(record,status=201,body=body,resource_type="compliance_override",resource_id=override.pk)
                return Response(body,status=201)
        except IdempotencyConflict:return safe_error("IDEMPOTENCY_CONFLICT",409)
        except ValueError as exc:return safe_error(str(exc),409 if str(exc)=="VERSION_CONFLICT" else 400)

class OverrideApprovalView(APIView):
    permission_classes=(IsComplianceManager,)
    @extend_schema(parameters=VERSIONED_PARAMETERS)
    def post(self,request,override_id):
        override=ComplianceOverride.objects.filter(pk=override_id,account__organization_id__in=authorized_organization_ids(request.user,"compliance_manager")).first()
        if not override:return safe_error("RESOURCE_NOT_FOUND",404)
        key,version,request_id=_headers(request,True)
        if not key:return safe_error("COMMAND_HEADERS_REQUIRED",422)
        try:
            with transaction.atomic():
                override=ComplianceOverride.objects.select_for_update().get(pk=override.pk)
                record,fresh=_begin(request,override.account.organization_id,f"/api/v1/admin/compliance/overrides/{override.pk}/approve",key,{"override_id":str(override.pk),"expected_version":version})
                if replay:=_replay(record,fresh):return replay
                if override.requested_at.isoformat()!=version:raise ValueError("VERSION_CONFLICT")
                override=approve_override(override.pk,request.user)
                body={"override_id":str(override.pk),"status":"APPROVED","approved_at":_iso(override.approved_at)}
                _audit(request,request_id,"compliance.override.approved","compliance_override",override.pk,context={"account_id":str(override.account_id),"control":override.control})
                complete_idempotent_request(record,status=200,body=body,resource_type="compliance_override",resource_id=override.pk)
                return Response(body)
        except (IdempotencyConflict,ValueError) as exc:return safe_error(str(exc),409)
