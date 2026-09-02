from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
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
from apps.trading.models import CanonicalExecution, ExecutionGovernanceChange, ExecutionProviderCapability, ExecutionProviderRecord, ExecutionQualityReport, ExecutionReconciliationRun, ExecutionRoutingDecision, TradingOrder, UnknownExecutionOutcome
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
        gateway=FixExecutionGateway()
        for message_type in ("A","5","0","1","2","4","D","F","G","8","9","j"):
            self.assertFalse(gateway.build_fixture(message_type)["network"])
        gateway.transition("CONNECTING");gateway.transition("LOGGED_ON")
        self.assertEqual(gateway.receive({"35":"0","34":"3"})["action"],"RESEND_REQUEST")
        gateway.session.state="LOGGED_ON";gateway.session.incoming_seq=1
        self.assertEqual(gateway.receive({"35":"8","34":"1","17":"exec-1"})["business_effects"],1)
        self.assertEqual(gateway.receive({"35":"8","34":"1","43":"Y","17":"exec-1"})["business_effects"],0)
        with self.assertRaisesMessage(RuntimeError,"FIX_LIVE_SESSION_DISABLED"):gateway.send("D")

    def test_paper_adapter_is_deterministic_and_no_network(self):
        provider=PaperExecutionProvider("paper-fixture",{"BTC-USD":"100"});order=self.order()
        self.assertEqual(provider.submit_order(order).state,"FILLED");self.assertEqual(provider.health()["outbound_live_requests"],0)
        self.assertEqual(provider.replace_order("fixture:1",{"quantity":"1"})["state"],"REPLACED")
        self.assertEqual(provider.resolve_unknown_operation("fixture:1")["state"],"NOT_FOUND")

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

    def test_provider_capability_records_are_enforced(self):
        router=SmartOrderRouter();ExecutionProviderCapability.objects.filter(provider_id="simulation",capability_type="MARKET_ORDER").update(enabled=False)
        result=router.route(self.user,{**self.payload(),"market_snapshot_hash":digest("m"),"pricing_snapshot_hash":digest("p"),"risk_snapshot_hash":digest("r")},persist=False)
        self.assertFalse(result["routable"]);self.assertIn("PROVIDER_ORDER_TYPE_UNSUPPORTED",result["exclusions"][0]["reasons"])

    def test_route_and_quality_evidence_are_immutable(self):
        order=self.order(filled_quantity=2,average_fill_price=101,state="FILLED")
        result=SmartOrderRouter().route(self.user,{**self.payload(),"market_snapshot_hash":digest("m"),"pricing_snapshot_hash":digest("p"),"risk_snapshot_hash":digest("r")},order=order)
        decision=ExecutionRoutingDecision.objects.get(pk=result["decision_id"]);decision.status="DENIED"
        with self.assertRaisesMessage(ValueError,"ROUTING_DECISION_IMMUTABLE"):decision.save()
        from apps.trading.execution_authority import record_quality
        report=record_quality(order);report.quality_state="ALTERED"
        with self.assertRaisesMessage(ValueError,"EXECUTION_QUALITY_IMMUTABLE"):report.save()
        order.average_fill_price=102;order.save(update_fields=("average_fill_price","updated_at"));new_report=record_quality(order)
        self.assertEqual(new_report.revision,2);self.assertEqual(new_report.supersedes,report)

    def test_quality_get_is_read_only(self):
        order=self.order(filled_quantity=2,average_fill_price=101,state="FILLED")
        SmartOrderRouter().route(self.user,{**self.payload(),"market_snapshot_hash":digest("m"),"pricing_snapshot_hash":digest("p"),"risk_snapshot_hash":digest("r")},order=order)
        self.assertEqual(self.client.get(f"/api/v1/execution/quality/{order.id}").status_code,404)
        self.assertEqual(ExecutionQualityReport.objects.count(),0)

    def test_paper_enable_requires_independent_manager_checker(self):
        managers=Group.objects.create(name="execution_manager");first=self.user;first.groups.add(managers)
        provider=seed_fixture_capabilities()[0][1];provider.enabled=False;provider.save(update_fields=("enabled","updated_at"))
        version=provider.updated_at.isoformat().replace("+00:00","Z")
        maker_headers={"HTTP_IDEMPOTENCY_KEY":"paper-enable-maker","HTTP_X_REQUEST_ID":"cf69152c-93d8-4888-804b-4c8846f41001","HTTP_IF_MATCH":version}
        response=self.client.post(f"/api/v1/operator/execution/providers/{provider.pk}/paper-enable",{"reason":"fixture certification"},format="json",**maker_headers)
        self.assertEqual(response.status_code,202);self.assertFalse(response.data["enabled"])
        replay=self.client.post(f"/api/v1/operator/execution/providers/{provider.pk}/paper-enable",{"reason":"fixture certification"},format="json",**maker_headers)
        self.assertEqual(replay.status_code,202);self.assertEqual(replay.data,response.data)
        self.assertEqual(self.client.post(f"/api/v1/operator/execution/providers/{provider.pk}/paper-enable",{"reason":"self approval"},format="json",HTTP_IDEMPOTENCY_KEY="paper-enable-self",HTTP_X_REQUEST_ID="cf69152c-93d8-4888-804b-4c8846f41002",HTTP_IF_MATCH=version).status_code,409)
        checker=get_user_model().objects.create_user(email="checker@example.test",password="x",phone_number="+15550000102");checker.groups.add(managers);self.client.force_authenticate(checker)
        checker_headers={"HTTP_IDEMPOTENCY_KEY":"paper-enable-checker","HTTP_X_REQUEST_ID":"cf69152c-93d8-4888-804b-4c8846f41003","HTTP_IF_MATCH":version}
        response=self.client.post(f"/api/v1/operator/execution/providers/{provider.pk}/paper-enable",{"reason":"independent check"},format="json",**checker_headers)
        self.assertEqual(response.status_code,200);provider.refresh_from_db();self.assertTrue(provider.enabled)
        replay=self.client.post(f"/api/v1/operator/execution/providers/{provider.pk}/paper-enable",{"reason":"independent check"},format="json",**checker_headers)
        self.assertEqual(replay.status_code,200);self.assertEqual(replay.data,response.data)
        self.assertEqual(ExecutionGovernanceChange.objects.count(),1)

    def test_operator_reconciliation_command_is_durably_idempotent(self):
        operators=Group.objects.create(name="execution_operator");self.user.groups.add(operators)
        headers={"HTTP_IDEMPOTENCY_KEY":"reconcile-test-key","HTTP_X_REQUEST_ID":"cf69152c-93d8-4888-804b-4c8846f41004"}
        first=self.client.post("/api/v1/operator/execution/reconciliation",{},format="json",**headers)
        replay=self.client.post("/api/v1/operator/execution/reconciliation",{},format="json",**headers)
        self.assertEqual(first.status_code,201);self.assertEqual(replay.status_code,201);self.assertEqual(replay.data,first.data)
        self.assertEqual(ExecutionReconciliationRun.objects.count(),1)

    def test_unknown_api_cannot_force_success_with_caller_evidence(self):
        operators=Group.objects.create(name="execution_operator");self.user.groups.add(operators)
        order=self.order();preview_route(self.user,self.payload(),persist=True,order=order);record_ambiguous_outcome(order,"simulation")
        outcome=UnknownExecutionOutcome.objects.get()
        response=self.client.post(f"/api/v1/operator/execution/unknown/{outcome.id}/reconcile",{"evidence_hash":"a"*64},format="json")
        self.assertEqual(response.status_code,409);outcome.refresh_from_db();self.assertEqual(outcome.state,"UNRESOLVED")

    def test_route_correction_is_additive_and_linked(self):
        order=self.order();first=SmartOrderRouter().route(self.user,{**self.payload(),"market_snapshot_hash":digest("m1"),"pricing_snapshot_hash":digest("p1"),"risk_snapshot_hash":digest("r1")},order=order)
        prior=ExecutionRoutingDecision.objects.get(pk=first["decision_id"])
        second=SmartOrderRouter().route(self.user,{**self.payload(),"market_snapshot_hash":digest("m2"),"pricing_snapshot_hash":digest("p2"),"risk_snapshot_hash":digest("r2")},order=order,supersedes=prior)
        correction=ExecutionRoutingDecision.objects.get(pk=second["decision_id"])
        self.assertEqual(correction.revision,2);self.assertEqual(correction.supersedes,prior);self.assertEqual(order.routing_decisions.count(),2)
