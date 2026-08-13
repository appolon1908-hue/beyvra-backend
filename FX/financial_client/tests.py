import tempfile
import json
import uuid
from pathlib import Path
from unittest.mock import Mock
from django.test import SimpleTestCase,override_settings
import requests
from .client import FinancialContext,FinancialFeatureDisabled,FinancialServiceClient,FinancialServiceError,UnknownFinancialOutcome,CircuitBreaker,CircuitOpen,FinancialContractUnavailable
from .metrics import FAILURES, IDEMPOTENCY_CONFLICTS, UNKNOWN_OUTCOMES


def response(status, body):
    result=Mock(status_code=status); result.json.return_value=body; return result


class DeterministicFinancialAdapter:
    """In-memory authority used only to prove idempotency without real effects."""
    def __init__(self):
        self.operations={}; self.business_effects=0; self.call_count=0
    def request(self, method, url, **kwargs):
        self.call_count += 1
        key=kwargs["headers"]["Idempotency-Key"]
        payload=json.dumps(kwargs.get("json"),sort_keys=True,separators=(",",":"))
        prior=self.operations.get(key)
        if prior and prior[0] != payload:
            return response(409,{"code":"IDEMPOTENCY_CONFLICT","request_id":"must-not-leak"})
        if not prior:
            self.business_effects += 1
            self.operations[key]=(payload,{"operation_ref":f"test-{self.business_effects}"})
        return response(200,self.operations[key][1])

class FinancialServiceClientTests(SimpleTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name)
        for name in ("client.crt","client.key","ca.crt"): (root/name).write_text("test",encoding="utf-8")
        self.override=override_settings(FINANCIAL_SERVICE_URL="https://financial-mtls:8443/",FINANCIAL_SERVICE_CLIENT_CERT=str(root/"client.crt"),FINANCIAL_SERVICE_CLIENT_KEY=str(root/"client.key"),FINANCIAL_SERVICE_CA_CERT=str(root/"ca.crt")); self.override.enable()
        self.context=FinancialContext(uuid.uuid4(),uuid.uuid4(),"req-client-test",uuid.uuid4())
    def tearDown(self): self.override.disable(); self.temp.cleanup()
    def test_context_headers_and_mtls_are_always_supplied(self):
        response=Mock(status_code=200); response.json.return_value={"results":[]}; session=Mock(); session.request.return_value=response
        client=FinancialServiceClient(session=session); client.list_wallets(self.context)
        call=session.request.call_args
        self.assertEqual(call.args[0],"GET"); self.assertEqual(call.kwargs["headers"]["X-Tenant-Ref"],str(self.context.tenant_ref)); self.assertEqual(len(call.kwargs["cert"]),2); self.assertTrue(call.kwargs["verify"].endswith("ca.crt"))
    def test_feature_disabled_is_not_treated_as_success(self):
        response=Mock(status_code=503); response.json.return_value={"code":"FEATURE_DISABLED","detail":"disabled"}; session=Mock(); session.request.return_value=response
        with self.assertRaises(FinancialFeatureDisabled): FinancialServiceClient(session=session).request_withdrawal(self.context,{"amount_atomic":"1"},"idem")
    def test_feature_disabled_is_expected_and_never_opens_or_counts_as_failure(self):
        breaker=CircuitBreaker(threshold=2)
        session=Mock(); session.request.return_value=response(503,{"code":"FEATURE_DISABLED"})
        before=FAILURES.labels(category="FINANCIAL_SERVICE_ERROR")._value.get()
        client=FinancialServiceClient(session=session,breaker=breaker)
        for index in range(100):
            with self.assertRaises(FinancialFeatureDisabled):
                client.request_withdrawal(self.context,{"amount":"1.00"},f"disabled-{index}")
        self.assertEqual(breaker.state,"CLOSED")
        self.assertEqual(FAILURES.labels(category="FINANCIAL_SERVICE_ERROR")._value.get(),before)
    def test_no_financial_database_alias_exists(self):
        from django.conf import settings
        self.assertEqual(set(settings.DATABASES),{"default"})
    def test_mutation_timeout_is_unknown_and_never_retried(self):
        before=UNKNOWN_OUTCOMES._value.get()
        session=Mock(); session.request.side_effect=requests.Timeout()
        with self.assertRaises(UnknownFinancialOutcome): FinancialServiceClient(session=session).request_transfer(self.context,{"amount":"1.00"},"key")
        self.assertEqual(session.request.call_count,1)
        self.assertEqual(UNKNOWN_OUTCOMES._value.get(),before+1)
    def test_safe_read_retries_are_bounded(self):
        session=Mock(); session.request.side_effect=requests.ConnectionError()
        with self.assertRaises(Exception): FinancialServiceClient(session=session).list_wallets(self.context)
        self.assertEqual(session.request.call_count,3)
    def test_circuit_breaker_opens_and_recovers_half_open(self):
        now=[0.0]; breaker=CircuitBreaker(threshold=2,recovery_seconds=30,clock=lambda:now[0])
        breaker.failure(); breaker.failure()
        with self.assertRaises(CircuitOpen): breaker.before_request()
        now[0]=31
        breaker.before_request(); self.assertEqual(breaker.state,"HALF_OPEN")
        with self.assertRaises(CircuitOpen): breaker.before_request()
        breaker.success(); self.assertEqual(breaker.state,"CLOSED")
    def test_missing_authoritative_operations_never_make_network_request(self):
        session=Mock()
        with self.assertRaises(FinancialContractUnavailable): FinancialServiceClient(session=session).settle_trade(self.context,{},"key")
        session.request.assert_not_called()
    def test_mtls_failures_are_denied_without_retry_or_tls_bypass(self):
        for fixture in ("expired certificate","wrong CA","wrong service identity"):
            session=Mock(); session.request.side_effect=requests.exceptions.SSLError(f"synthetic {fixture}")
            with self.assertRaises(Exception) as raised:
                FinancialServiceClient(session=session).list_wallets(self.context)
            self.assertEqual(raised.exception.code,"MTLS_AUTHENTICATION_FAILED")
            self.assertEqual(session.request.call_count,1)
            self.assertNotIn("verify=False",str(session.request.call_args))

    def test_read_overall_deadline_bounds_retries(self):
        now=[0.0]
        def clock(): return now[0]
        session=Mock()
        def timeout_once(*args,**kwargs):
            now[0]=2.0
            raise requests.Timeout()
        session.request.side_effect=timeout_once
        with override_settings(FINANCIAL_SERVICE_OVERALL_DEADLINE_SECONDS=1):
            client=FinancialServiceClient(session=session,breaker=CircuitBreaker(clock=clock),clock=clock)
            with self.assertRaises(FinancialServiceError) as raised:
                client.list_wallets(self.context)
        self.assertEqual(raised.exception.code,"TRANSIENT_UNAVAILABLE")
        self.assertEqual(session.request.call_count,1)
        connect_timeout,request_timeout=session.request.call_args.kwargs["timeout"]
        self.assertGreater(connect_timeout,0); self.assertGreater(request_timeout,0)
        self.assertLessEqual(connect_timeout+request_timeout,1)

    def test_safe_read_retries_approved_500_and_503_then_succeeds(self):
        session=Mock(); session.request.side_effect=[
            response(503,{"code":"TEMPORARY"}),response(500,{"code":"TEMPORARY"}),
            response(200,{"results":[]}),
        ]
        self.assertEqual(FinancialServiceClient(session=session).list_wallets(self.context),{"results":[]})
        self.assertEqual(session.request.call_count,3)

    def test_mutation_500_and_503_are_never_blindly_retried(self):
        for status in (500,503):
            session=Mock(); session.request.return_value=response(status,{"code":"INTERNAL_PROVIDER_DETAIL","request_id":"hidden"})
            with self.assertRaises(FinancialServiceError) as raised:
                FinancialServiceClient(session=session).request_transfer(self.context,{"amount":"1.00"},f"key-{status}")
            self.assertEqual(raised.exception.code,"FINANCIAL_SERVICE_ERROR")
            self.assertEqual(raised.exception.detail,"Financial service request failed.")
            self.assertEqual(session.request.call_count,1)

    def test_deterministic_adapter_same_key_has_one_effect_and_conflict_is_safe(self):
        adapter=DeterministicFinancialAdapter(); client=FinancialServiceClient(session=adapter)
        first=client.request_transfer(self.context,{"amount":"1.00","asset":"USD"},"same-key")
        duplicate=client.request_transfer(self.context,{"amount":"1.00","asset":"USD"},"same-key")
        self.assertEqual(first,duplicate)
        self.assertEqual(adapter.business_effects,1)
        before=IDEMPOTENCY_CONFLICTS._value.get()
        with self.assertRaises(FinancialServiceError) as raised:
            client.request_transfer(self.context,{"amount":"2.00","asset":"USD"},"same-key")
        self.assertEqual(raised.exception.code,"IDEMPOTENCY_CONFLICT")
        self.assertEqual(IDEMPOTENCY_CONFLICTS._value.get(),before+1)
        self.assertEqual(adapter.business_effects,1)

    def test_lost_response_after_commit_stays_unknown_across_client_restart(self):
        committed={"effects":0,"keys":set()}
        session=Mock()
        def commit_then_lose(*args,**kwargs):
            key=kwargs["headers"]["Idempotency-Key"]
            if key not in committed["keys"]:
                committed["keys"].add(key); committed["effects"] += 1
            raise requests.Timeout("synthetic response loss after commit")
        session.request.side_effect=commit_then_lose
        with self.assertRaises(UnknownFinancialOutcome):
            FinancialServiceClient(session=session).request_transfer(self.context,{"amount":"1.00"},"lost-after-commit")
        restarted_session=Mock()
        restarted=FinancialServiceClient(session=restarted_session)
        with self.assertRaises(FinancialContractUnavailable):
            restarted.resolve_unknown_outcome(self.context,"lost-after-commit")
        restarted_session.request.assert_not_called()
        self.assertEqual(committed["effects"],1)

    def test_connection_refused_on_mutation_is_unknown_and_not_retried(self):
        session=Mock(); session.request.side_effect=requests.ConnectionError("synthetic refused")
        with self.assertRaises(UnknownFinancialOutcome):
            FinancialServiceClient(session=session).request_withdrawal(self.context,{"amount":"1.00"},"connection-refused")
        self.assertEqual(session.request.call_count,1)

    def test_late_known_response_is_not_duplicated(self):
        now=[0.0]
        def clock(): return now[0]
        adapter=DeterministicFinancialAdapter()
        original=adapter.request
        def late_response(*args,**kwargs):
            now[0]=0.9
            return original(*args,**kwargs)
        adapter.request=late_response
        with override_settings(FINANCIAL_SERVICE_OVERALL_DEADLINE_SECONDS=1):
            client=FinancialServiceClient(session=adapter,breaker=CircuitBreaker(clock=clock),clock=clock)
            result=client.request_transfer(self.context,{"amount":"1.00"},"late-known")
        self.assertEqual(result["operation_ref"],"test-1")
        self.assertEqual(adapter.business_effects,1)

    def test_business_denials_are_not_retried_and_map_to_safe_categories(self):
        fixtures=((400,"VALIDATION_FAILED","VALIDATION_ERROR"),(403,"TENANT_MISMATCH","RESTRICTION"),(409,"IDEMPOTENCY_CONFLICT","IDEMPOTENCY_CONFLICT"))
        for status,raw,safe in fixtures:
            session=Mock(); session.request.return_value=response(status,{"code":raw,"detail":"unsafe provider detail","request_id":"hidden"})
            with self.assertRaises(FinancialServiceError) as raised:
                FinancialServiceClient(session=session).request_transfer(self.context,{"amount":"1.00"},f"business-{status}")
            self.assertEqual(raised.exception.code,safe)
            self.assertEqual(raised.exception.detail,"Financial service request failed.")
            self.assertEqual(session.request.call_count,1)

    def test_observability_labels_are_bounded_and_contain_no_path_or_identity(self):
        from .metrics import DURATION, REQUESTS
        self.assertEqual(REQUESTS._labelnames,("method","outcome"))
        self.assertEqual(FAILURES._labelnames,("category",))
        self.assertEqual(DURATION._labelnames,("method",))

    def test_invalid_mutation_key_or_payload_never_reaches_network(self):
        session=Mock(); client=FinancialServiceClient(session=session)
        for key,payload in (("",{}),("contains space",{}),("valid-key",None)):
            with self.assertRaises(FinancialServiceError) as raised:
                client.request_transfer(self.context,payload,key)
            self.assertEqual(raised.exception.code,"VALIDATION_ERROR")
        session.request.assert_not_called()
