from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from integrations.models import Organization,OrganizationMembership
from wallet.constants import DEMO_WALLET_NAME
from wallet.models import Currency,Wallet
from trade.demo_engine import settle_due_orders
from trade.models import Trade

class DemoFinancialIsolationTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(email="demo-financial-isolation@example.invalid",password="test-pass",phone_number="+12025550181")
        self.organization=Organization.objects.create(name="Demo isolation tenant")
        OrganizationMembership.objects.create(user=self.user,organization=self.organization)
        currency=Currency.objects.create(name="Demo Isolation Dollar",symbol="DID",longer_name="Demo Isolation Dollar")
        self.wallet=Wallet.objects.create(user=self.user,organization=self.organization,name=DEMO_WALLET_NAME,currency=currency,balance=Decimal("10000"),is_real=False)
        self.client=APIClient(); self.client.force_authenticate(self.user)

    @patch("financial_client.client.FinancialServiceClient._request")
    def test_refill_order_and_settlement_never_call_financial_service(self,financial_request):
        refill=self.client.post("/api/v1/demo/wallet/refill",{},format="json",HTTP_IDEMPOTENCY_KEY="isolation-refill",HTTP_X_ORGANIZATION_ID=str(self.organization.id))
        self.assertEqual(refill.status_code,200)
        with patch("trade.demo_engine.quote",return_value=(Decimal("100"),timezone.now())):
            order=self.client.post("/api/v1/demo/orders",{"symbol":"BTCUSDT","direction":"up","amount":"10","duration":5},format="json",HTTP_IDEMPOTENCY_KEY="isolation-order",HTTP_X_ORGANIZATION_ID=str(self.organization.id))
        self.assertEqual(order.status_code,201)
        trade=Trade.objects.get(pk=order.data["id"]); trade.expires_at=timezone.now()-timedelta(seconds=1); trade.save(update_fields=["expires_at"])
        with patch("trade.demo_engine.quote",return_value=(Decimal("101"),timezone.now())):
            self.assertEqual(settle_due_orders(),1)
        financial_request.assert_not_called()
        self.assertFalse(Wallet.objects.get(pk=self.wallet.pk).is_real)

    def test_real_wallet_identifier_is_not_a_demo_wallet_identifier(self):
        response=self.client.get("/api/v1/demo/wallet",HTTP_X_ORGANIZATION_ID=str(self.organization.id),HTTP_X_FINANCIAL_WALLET_ID="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.data["code"],"FINANCIAL_WALLET_ID_NOT_ACCEPTED")
