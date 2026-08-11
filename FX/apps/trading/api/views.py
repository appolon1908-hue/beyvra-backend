from decimal import Decimal, InvalidOperation
from integrations.models import OrganizationMembership
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.compliance.models import ComplianceProfile
from apps.compliance.services import get_trading_eligibility
from apps.trading.domain.orders import OrderState
from apps.trading.models import TradingOrder
from .errors import error_response

def _context(request, *, lock=False):
    org = OrganizationMembership.objects.filter(user=request.user).order_by("id").values_list("organization_id", flat=True).first()
    query=ComplianceProfile.objects.select_for_update() if lock else ComplianceProfile.objects
    return org, query.filter(organization_id=org, user=request.user).first() if org else None

def _eligibility(request, context_ref="", *, lock=False):
    _, profile = _context(request,lock=lock)
    if not profile: return None
    return get_trading_eligibility(profile, context_ref=context_ref)

def _denied(request, decision):
    code = decision.reason_codes[0] if decision and decision.reason_codes else "KYC_REQUIRED"
    return error_response(request, code, 403, {"eligibility_result": decision.result if decision else "DENIED", "reason_codes": list(decision.reason_codes) if decision else [code], "policy_version": decision.policy_version if decision else "compliance-2026-08-11.v1"})

def _serialize(order):
    return {"id":str(order.pk),"instrument":order.instrument_id,"order_type":order.order_type,"side":order.side,"quantity":str(order.quantity),"filled_quantity":"0","state":order.state,"simulation":True,"eligibility_policy_version":order.eligibility_policy_version,"eligibility_result":order.eligibility_result,"eligibility_reason_codes":order.eligibility_reason_codes,"evaluated_at":order.eligibility_evaluated_at}

class OrderCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        org, _ = _context(request)
        return Response({"results":[_serialize(x) for x in TradingOrder.objects.filter(tenant_ref=str(org), subject_ref=str(request.user.pk), simulation=True).order_by("-created_at")[:100]]})
    def post(self, request):
        return self._post_atomic(request)
    @transaction.atomic
    def _post_atomic(self, request):
        if request.headers.get("X-Beyvra-Simulation-Mode", "").lower() != "true": return error_response(request, "FEATURE_DISABLED", 503)
        decision = _eligibility(request,lock=True)
        if not decision or decision.result != "ALLOWED": return _denied(request, decision)
        try: quantity = Decimal(str(request.data.get("quantity")))
        except (InvalidOperation, TypeError): return error_response(request, "INVALID_ORDER", 400)
        key = request.headers.get("Idempotency-Key", "")
        org, profile = _context(request,lock=True)
        if key:
            existing = TradingOrder.objects.filter(tenant_ref=str(org), subject_ref=str(request.user.pk), idempotency_key=key).first()
            if existing:
                same=(existing.instrument_id==str(request.data.get("instrument",""))[:64] and existing.order_type==request.data.get("order_type","MARKET") and existing.side==request.data.get("side","BUY") and existing.quantity==quantity)
                return Response(_serialize(existing), status=200) if same else error_response(request,"IDEMPOTENCY_CONFLICT",409)
        if quantity <= 0 or request.data.get("side") not in ("BUY","SELL") or request.data.get("order_type","MARKET") not in ("MARKET","LIMIT","STOP","STOP_LIMIT"): return error_response(request,"INVALID_ORDER",400)
        if not request.data.get("instrument"): return error_response(request,"INVALID_ORDER",400)
        order = TradingOrder.objects.create(tenant_ref=str(org),subject_ref=str(request.user.pk),account_ref=str(profile.pk),instrument_id=str(request.data.get("instrument",""))[:64],order_type=request.data.get("order_type","MARKET"),side=request.data.get("side","BUY"),quantity=quantity,state=OrderState.PENDING,simulation=True,idempotency_key=key,eligibility_policy_version=decision.policy_version,eligibility_result=decision.result,eligibility_reason_codes=list(decision.reason_codes),eligibility_evaluated_at=decision.evaluated_at)
        return Response(_serialize(order), status=201)

class OrderPreviewView(APIView):
    permission_classes = (IsAuthenticated,)
    def post(self, request):
        if request.headers.get("X-Beyvra-Simulation-Mode", "").lower() != "true": return error_response(request, "FEATURE_DISABLED", 503)
        decision = _eligibility(request, "preview")
        if not decision or decision.result != "ALLOWED": return _denied(request, decision)
        return Response({"estimated_fee":"0","available_simulated_balance":"0","simulation":True,"eligibility_result":decision.result,"eligibility_policy_version":decision.policy_version,"eligibility_reason_codes":list(decision.reason_codes),"evaluated_at":decision.evaluated_at})

class OrderDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, order_id):
        order = TradingOrder.objects.filter(pk=order_id, subject_ref=str(request.user.pk), simulation=True).first()
        return Response(_serialize(order)) if order else error_response(request,"RESOURCE_NOT_FOUND",404)

class OrderCancelView(APIView):
    permission_classes = (IsAuthenticated,)
    def post(self, request, order_id): return error_response(request,"FEATURE_DISABLED",503)

class EmptyCollectionView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request): return Response({"results": []})
class EmptyDetailView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request, **kwargs): return error_response(request,"RESOURCE_NOT_FOUND",404)
class FeesView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request): return Response({"results":[],"real_trading_enabled":False})
