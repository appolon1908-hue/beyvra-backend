import hashlib, json
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import enqueue_event
from apps.trading.models import ExecutionRouteCandidate, ExecutionRoutingDecision
from .capabilities import BrokerCapabilityAuthority, VenueCapabilityAuthority, seed_fixture_capabilities
from .governance import ExecutionProviderGovernance
from .health import ProviderHealthService
from .policy import BestExecutionPolicyAuthority
from apps.foundation.observability import EXECUTION_ROUTE_CANDIDATES, EXECUTION_ROUTE_REJECTIONS, EXECUTION_ROUTE_REQUESTS, EXECUTION_ROUTE_SELECTED


def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()


class SmartOrderRouter:
    def __init__(self):
        self.brokers=BrokerCapabilityAuthority(); self.venues=VenueCapabilityAuthority(); self.governance=ExecutionProviderGovernance(); self.health=ProviderHealthService(); self.policies=BestExecutionPolicyAuthority()
        self.fixture_providers,self.fixture_venue=seed_fixture_capabilities()

    def generate_candidates(self, request):
        providers, venue=self.fixture_providers,self.fixture_venue; mode=request["mode"]
        candidates=[]
        for provider in providers:
            if provider.mode != mode: continue
            economics=self._economics(provider,request)
            reasons=self.governance.reasons(provider,mode)
            reasons += self.venues.validate(venue,asset_class=request["asset_class"],order_type=request["order_type"],time_in_force=request["time_in_force"],quantity=request["quantity"],price=request.get("limit_price"))
            if not self.health.is_routable(provider) and "PROVIDER_UNHEALTHY" not in reasons: reasons.append("PROVIDER_UNHEALTHY")
            candidates.append({"provider":provider,"venue":venue,"economics":economics,"reasons":sorted(set(reasons))})
        return candidates

    def _economics(self,provider,request):
        ref=Decimal(request["reference_price"]); quantity=Decimal(request["quantity"])
        adjustments={"simulation":Decimal("0"),"paper-a":Decimal("-0.0002"),"paper-b":Decimal("0.0001")}
        fee_rates={"simulation":Decimal("0.001"),"paper-a":Decimal("0.0015"),"paper-b":Decimal("0.0005")}
        latency={"simulation":1,"paper-a":10,"paper-b":25}; fills={"simulation":Decimal("1"),"paper-a":Decimal("0.92"),"paper-b":Decimal("0.98")}
        sign=Decimal("1") if request["side"]=="BUY" else Decimal("-1")
        expected=ref*(Decimal("1")+sign*adjustments[provider.provider_id]); fee=expected*quantity*fee_rates[provider.provider_id]
        return {"expected_price":expected,"expected_fee":fee,"expected_slippage":abs(expected-ref),"available_quantity":quantity,
            "fill_probability":fills[provider.provider_id],"latency_ms":latency[provider.provider_id],"price_score":Decimal("1")-abs(expected-ref)/ref,
            "fee_score":Decimal("1")-min(fee/(ref*quantity),Decimal("1")),"latency_score":Decimal("1")-Decimal(latency[provider.provider_id])/Decimal("1000"),
            "fill_score":fills[provider.provider_id],"liquidity_score":Decimal("1"),"reliability_score":fills[provider.provider_id],"impact_score":Decimal("1")}

    def filter_candidates(self,candidates): return [x for x in candidates if not x["reasons"]]
    def score_candidates(self,candidates,policy):
        for item in candidates: item["score"]=self.policies.score(policy,item["economics"]) if not item["reasons"] else Decimal("-1")
        return candidates
    def select_route(self,candidates):
        eligible=self.filter_candidates(candidates)
        return sorted(eligible,key=lambda x:(-x["score"],x["economics"]["expected_fee"],x["provider"].priority,x["provider"].provider_id))[0] if eligible else None
    def explain_selection(self,selected):
        return "HIGHEST_POLICY_SCORE_THEN_COST_PRIORITY_CODE" if selected else "ORDER_NOT_ROUTABLE"

    @transaction.atomic
    def route(self,user,request,order=None,persist=True):
        if request["mode"]=="LIVE": raise ValueError("FEATURE_DISABLED")
        policy=self.policies.active(request["asset_class"],request["mode"]); candidates=self.score_candidates(self.generate_candidates(request),policy); selected=self.select_route(candidates)
        safe=[{"provider_id":x["provider"].provider_id,"venue_id":x["venue"].venue_id,"eligible":not x["reasons"],"rejection_reasons":x["reasons"],
            "expected_price":str(x["economics"]["expected_price"]),"expected_fee":str(x["economics"]["expected_fee"]),"estimated_latency_ms":x["economics"]["latency_ms"],
            "estimated_fill_probability":str(x["economics"]["fill_probability"]),"score":str(x["score"])} for x in candidates]
        evidence={"request":request,"candidates":safe,"policy_id":str(policy.id),"policy_version":policy.policy_version,"selected":selected["provider"].provider_id if selected else None}
        result={"routable":bool(selected),"mode":request["mode"],"eligible_route_count":len(self.filter_candidates(candidates)),"reason_codes":[] if selected else ["ORDER_NOT_ROUTABLE"],
            "selected_route_summary":{"provider_id":selected["provider"].provider_id,"venue_id":selected["venue"].venue_id} if selected else None,
            "estimated_execution_price":str(selected["economics"]["expected_price"]) if selected else None,"estimated_fees":str(selected["economics"]["expected_fee"]) if selected else None,
            "estimated_slippage":str(selected["economics"]["expected_slippage"]) if selected else None,"policy_version":policy.policy_version,"evidence_hash":digest(evidence),
            "candidates":safe,"exclusions":[{"provider_id":x["provider_id"],"reasons":x["rejection_reasons"]} for x in safe if not x["eligible"]],
            "simulation":request["mode"]=="SIMULATION","paper":request["mode"]=="PAPER"}
        EXECUTION_ROUTE_REQUESTS.labels(request["asset_class"],request["order_type"],"selected" if selected else "denied",request["mode"].lower()).inc()
        for item in candidates:
            outcome="eligible" if not item["reasons"] else "rejected"; EXECUTION_ROUTE_CANDIDATES.labels(item["provider"].provider_id,request["asset_class"],request["order_type"],outcome,request["mode"].lower()).inc()
            if item["reasons"]: EXECUTION_ROUTE_REJECTIONS.labels(item["provider"].provider_id,request["asset_class"],request["order_type"],item["reasons"][0].lower(),request["mode"].lower()).inc()
        if selected: EXECUTION_ROUTE_SELECTED.labels(selected["provider"].provider_id,selected["venue"].venue_type,request["asset_class"],request["order_type"],request["mode"].lower()).inc()
        if persist:
            decision=ExecutionRoutingDecision.objects.create(order=order,tenant_ref="default",subject_ref=str(user.pk),mode=request["mode"],status="SELECTED" if selected else "DENIED",
                selected_provider_id=selected["provider"].provider_id if selected else "",selected_venue_id=selected["venue"].venue_id if selected else "",policy_version=policy.policy_version,
                candidate_evidence=safe,exclusion_reasons=[x for x in safe if not x["eligible"]],market_snapshot_hash=request["market_snapshot_hash"],pricing_snapshot_hash=request["pricing_snapshot_hash"],
                risk_snapshot_hash=request["risk_snapshot_hash"],request_hash=digest(request),evidence_hash=result["evidence_hash"],selected_score=selected["score"] if selected else None,reference_price=request["reference_price"])
            for item in candidates:
                e=item["economics"]; ExecutionRouteCandidate.objects.create(decision=decision,provider=item["provider"],venue=item["venue"],mode=request["mode"],expected_price=e["expected_price"],
                    expected_fee=e["expected_fee"],expected_slippage=e["expected_slippage"],available_quantity=e["available_quantity"],estimated_fill_probability=e["fill_probability"],
                    estimated_latency_ms=e["latency_ms"],provider_health=item["provider"].health,score=item["score"],eligible=not item["reasons"],rejection_reasons=item["reasons"])
            correlation=__import__("uuid").UUID(str(request.get("correlation_id") or __import__("uuid").uuid4()))
            ApplicationAuditEvent.objects.create(actor_ref=str(user.pk),action="execution.route.selected" if selected else "execution.route.denied",resource_type="execution_route",resource_id=str(decision.decision_id),request_id="routing",correlation_id=correlation,context={"mode":request["mode"],"policy_version":policy.policy_version,"evidence_hash":result["evidence_hash"]},reason=self.explain_selection(selected),occurred_at=timezone.now())
            if selected: enqueue_event(aggregate_type="execution_route",aggregate_id=decision.decision_id,event_type="execution.route.selected.v1",payload={"order_id":str(order.id) if order else None,"mode":request["mode"],"policy_version":policy.policy_version,"simulation":request["mode"]=="SIMULATION"},tenant_ref="default",correlation_id=correlation)
            result["decision_id"]=str(decision.decision_id)
        return result
