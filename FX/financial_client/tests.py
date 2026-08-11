import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock
from django.test import SimpleTestCase,override_settings
import requests
from .client import FinancialContext,FinancialFeatureDisabled,FinancialServiceClient,UnknownFinancialOutcome,CircuitBreaker,CircuitOpen,FinancialContractUnavailable

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
    def test_no_financial_database_alias_exists(self):
        from django.conf import settings
        self.assertEqual(set(settings.DATABASES),{"default"})
    def test_mutation_timeout_is_unknown_and_never_retried(self):
        session=Mock(); session.request.side_effect=requests.Timeout()
        with self.assertRaises(UnknownFinancialOutcome): FinancialServiceClient(session=session).request_transfer(self.context,{"amount":"1.00"},"key")
        self.assertEqual(session.request.call_count,1)
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
        breaker.success(); self.assertEqual(breaker.state,"CLOSED")
    def test_missing_authoritative_operations_never_make_network_request(self):
        session=Mock()
        with self.assertRaises(FinancialContractUnavailable): FinancialServiceClient(session=session).settle_trade(self.context,{},"key")
        session.request.assert_not_called()
    def test_mtls_failures_are_denied_without_retry_or_tls_bypass(self):
        session=Mock(); session.request.side_effect=requests.exceptions.SSLError("synthetic wrong CA")
        with self.assertRaises(Exception) as raised:
            FinancialServiceClient(session=session).list_wallets(self.context)
        self.assertEqual(raised.exception.code,"MTLS_AUTHENTICATION_FAILED")
        self.assertEqual(session.request.call_count,1)
        self.assertNotIn("verify=False",str(session.request.call_args))
