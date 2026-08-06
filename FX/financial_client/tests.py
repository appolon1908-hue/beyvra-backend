import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock
from django.test import SimpleTestCase,override_settings
from .client import FinancialContext,FinancialFeatureDisabled,FinancialServiceClient

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
