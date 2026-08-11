from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.trading.execution_authority import preview_route, record_ambiguous_outcome
from apps.trading.execution_control.capabilities import VenueCapabilityAuthority, seed_fixture_capabilities
from apps.trading.execution_control.health import ProviderHealthService
from apps.trading.execution_control.policy import BestExecutionPolicyAuthority
from apps.trading.execution_control.quality import PriceImprovementAuthority, SlippageAuthority
from apps.trading.execution_control.reconciliation import ExecutionReconciler
from apps.trading.execution_control.recovery import ExecutionRecoveryService
from apps.trading.execution_control.router import SmartOrderRouter, digest
from apps.trading.execution_control.state import ExecutionStateAuthority
from apps.trading.models import CanonicalExecution, ExecutionProviderRecord, ExecutionRoutingDecision, TradingOrder, UnknownExecutionOutcome
from integrations.execution.fix_gateway import FixExecutionGateway
from integrations.execution.paper import PaperExecutionProvider


@override_settings(REAL_TRADING_ENABLED=False,EXTERNAL_EXECUTION_ENABLED=False,LIVE_BROKER_ROUTING_ENABLED=False,FIX_LIVE_SESSION_ENABLED=False,
    PAPER_TRADING_ALLOWED=True,SIMULATION_ALLOWED=True,ALL_EXECUTION_HALTED=False)
class ExecutionControlPlaneTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(email="control@example.test",password="x",phone_number="+15550000101")
        self.client=APIClient();self.client.force_authenticate(self.user)
    def payload(self,**extra):
        return {"instrument_id":"BTC-USD","side":"BUY","order_type":"MARKET","quantity":"2","reference_price":"100","mode":"SIMULATION","asset_class":"CRYPTO","time_in_force":"DAY",**extra}
    def order(self,**extra):
        data={"tenant_ref":"default","subject_ref":str(self.user.pk),"account_ref":f"sim:{self.user.pk}","instrument_id":"BTC-USD","order_type":"MARKET","side":"BUY","quantity":2,"simulation":True,**extra}
        return TradingOrder.objects.create(**data)

    def test_router_persists_ranked_candidates_and_hashes(self):
        order=self.order(); result=SmartOrderRouter().route(self.user,{**self.payload(),"market_snapshot_hash":digest("market"),"pricing_snapshot_hash":digest("price"),"risk_snapshot_hash":digest("risk")},order=order)
        self.assertTrue(result["routable"]); decision=ExecutionRoutingDecision.objects.get(pk=result["decision_id"])
        self.assertEqual(decision.candidates.count(),1);self.assertEqual(len(decision.evidence_hash),64);self.assertEqual(decision.selected_provider_id,"simulation")

    def test_multi_provider_paper_ranking_is_deterministic(self):
        result=SmartOrderRouter().route(self.user,{**self.payload(mode="PAPER"),"market_snapshot_hash":digest("m"),"pricing_snapshot_hash":digest("p"),"risk_snapshot_hash":digest("r")},persist=False)
        self.assertEqual(result["eligible_route_count"],2);self.assertEqual(result["selected_route_summary"]["provider_id"],"paper-b")

    def test_global_halt_and_stale_market_fail_closed(self):
        with override_settings(ALL_EXECUTION_HALTED=True):
            result=preview_route(self.user,self.payload());self.assertFalse(result["routable"])
        with self.assertRaisesMessage(ValueError,"MARKET_DATA_STALE"):preview_route(self.user,self.payload(market_data_stale=True))

    def test_venue_quantity_and_price_increment(self):
        _,venue=seed_fixture_capabilities(); authority=VenueCapabilityAuthority()
        self.assertEqual(authority.validate(venue,asset_class="CRYPTO",order_type="LIMIT",time_in_force="DAY",quantity="1.0000",price="100.01"),[])
        self.assertIn("INVALID_QUANTITY_INCREMENT",authority.validate(venue,asset_class="CRYPTO",order_type="LIMIT",time_in_force="DAY",quantity="1.00001",price="100.01"))

    def test_circuit_breaker_opens_after_three_failures_and_recovers(self):
        providers,_=seed_fixture_capabilities();provider=providers[0];service=ProviderHealthService()
        for _ in range(3):service.record_failure(provider)
        provider.refresh_from_db();self.assertEqual(service.evaluate(provider),"UNAVAILABLE");self.assertFalse(service.is_routable(provider))
        service.half_open(provider);service.record_success(provider);self.assertTrue(service.is_routable(provider))

    def test_side_aware_slippage_and_improvement(self):
        calc=SlippageAuthority(); improve=PriceImprovementAuthority()
        self.assertEqual(calc.calculate("BUY","100","101","2")["bps"],Decimal("100"))
        self.assertEqual(calc.calculate("SELL","100","99","2")["bps"],Decimal("100"))
        self.assertEqual(improve.calculate("BUY","100","99","2")["amount"],Decimal("2"))
        self.assertEqual(improve.calculate("SELL","100","101","2")["bps"],Decimal("100"))

    def test_execution_state_rejects_terminal_regression(self):
        providers,venue=seed_fixture_capabilities();execution=CanonicalExecution.objects.create(order=self.order(),provider=providers[0],venue=venue,state="ACKNOWLEDGED",quantity=2,remaining_quantity=2,mode="SIMULATION")
        execution=ExecutionStateAuthority().transition(execution,"FILLED",filled_quantity=2,remaining_quantity=0,average_price=100)
        with self.assertRaisesMessage(ValueError,"INVALID_EXECUTION_STATE_TRANSITION"):ExecutionStateAuthority().transition(execution,"WORKING")

    def test_unknown_requires_lookup_and_never_allows_failover(self):
        order=self.order();preview_route(self.user,self.payload(),persist=True,order=order);record_ambiguous_outcome(order,"simulation")
        outcome=UnknownExecutionOutcome.objects.get();unresolved=ExecutionRecoveryService().resolve_unknown(outcome,lambda _:None)
        self.assertEqual(unresolved.state,"UNRESOLVED");self.assertEqual(unresolved.lookup_attempts,1)
        resolved=ExecutionRecoveryService().resolve_unknown(unresolved,lambda _:{"evidence_hash":"a"*64});self.assertEqual(resolved.state,"RESOLVED")

    def test_fix_gateway_sequence_gap_and_duplicate_execution(self):
        gateway=FixExecutionGateway();gateway.transition("CONNECTING");gateway.transition("LOGGED_ON")
        self.assertEqual(gateway.receive({"35":"0","34":"3"})["action"],"RESEND_REQUEST")
        gateway.session.state="LOGGED_ON";gateway.session.incoming_seq=1
        self.assertEqual(gateway.receive({"35":"8","34":"1","17":"exec-1"})["business_effects"],1)
        self.assertEqual(gateway.receive({"35":"8","34":"1","43":"Y","17":"exec-1"})["business_effects"],0)
        with self.assertRaisesMessage(RuntimeError,"FIX_LIVE_SESSION_DISABLED"):gateway.send("D")

    def test_paper_adapter_is_deterministic_and_no_network(self):
        provider=PaperExecutionProvider("paper-fixture",{"BTC-USD":"100"});order=self.order()
        self.assertEqual(provider.submit_order(order).state,"FILLED");self.assertEqual(provider.health()["outbound_live_requests"],0)

    def test_customer_and_operator_api_matrix(self):
        for path in ("/api/v1/execution/capabilities","/api/v1/execution/capabilities/simulation","/api/v1/execution/venues","/api/v1/execution/venues/BEYVRA-SIM","/api/v1/execution/providers/status","/api/v1/execution/reports"):
            self.assertEqual(self.client.get(path).status_code,200,path)
        self.assertEqual(self.client.get("/api/v1/operator/execution/providers").status_code,403)
        self.user.is_staff=True;self.user.is_superuser=True;self.user.save();self.client.force_authenticate(self.user)
        for path in ("/api/v1/operator/execution/providers","/api/v1/operator/execution/providers/simulation","/api/v1/operator/execution/providers/simulation/capabilities","/api/v1/operator/execution/providers/simulation/health","/api/v1/operator/execution/venues","/api/v1/operator/execution/unknown","/api/v1/operator/execution/reconciliation"):
            self.assertEqual(self.client.get(path).status_code,200,path)

    def test_reconciliation_is_read_only_and_detects_unknown(self):
        order=self.order();preview_route(self.user,self.payload(),persist=True,order=order);record_ambiguous_outcome(order,"simulation")
        checks=ExecutionReconciler().inspect();self.assertEqual(checks["UNRESOLVED_UNKNOWN_OUTCOME"],1)
        run=ExecutionReconciler().run();self.assertEqual(run.status,"CRITICAL");self.assertEqual(UnknownExecutionOutcome.objects.filter(state="UNRESOLVED").count(),1)

    def test_policy_version_is_immutable_identity(self):
        policy=BestExecutionPolicyAuthority().active("CRYPTO","SIMULATION");self.assertEqual(policy.policy_version,"best-execution-technical-v2")

    @override_settings(LIVE_BROKER_ROUTING_ENABLED=True)
    def test_live_configuration_produces_zero_candidates(self):
        with self.assertRaisesMessage(ValueError,"LIVE_EXECUTION_DISABLED"):preview_route(self.user,self.payload())
        self.assertEqual(ExecutionRoutingDecision.objects.count(),0)
