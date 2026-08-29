import uuid
from decimal import Decimal
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from apps.trading.application.simulation import process_created_order
from apps.trading.models import TradingOrder, SimulatedTrade
from apps.trading.domain.orders import OrderState
from apps.foundation.models import OutboxEvent
from users.models import User
from apps.compliance.domain import AccountState, AmlState, JurisdictionState, KycState, SanctionsState
from apps.compliance.models import ComplianceProfile
from integrations.models import Organization, OrganizationMembership


SIMULATION = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
    SIMULATED_EXECUTION_PRICES={"BTC-USD": "100.00"},
    SIMULATED_EXECUTION_INLINE=False,
)


@SIMULATION
class OrderLifecycleV1ApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email=f"order-lifecycle-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}",
            password="testpassword"
        )
        org = Organization.objects.create(name=f"Org {uuid.uuid4()}")
        OrganizationMembership.objects.create(user=self.user, organization=org)
        ComplianceProfile.objects.create(
            user=self.user,
            organization=org,
            account_state=AccountState.ACTIVE,
            kyc_state=KycState.APPROVED,
            aml_state=AmlState.CLEARED,
            sanctions_state=SanctionsState.CLEAR,
            jurisdiction_state=JurisdictionState.SUPPORTED
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.headers = {"HTTP_X_BEYVRA_SIMULATION_MODE": "true"}

    def test_order_preview_and_creation_lifecycle(self):
        payload = {"instrument": "BTC-USD", "side": "BUY", "order_type": "MARKET", "quantity": "5"}
        res_prev = self.client.post("/api/v1/orders/preview", payload, format="json", **self.headers)
        self.assertEqual(res_prev.status_code, 200)
        self.assertEqual(res_prev.json()["decision"], "ALLOW")

        idemp_key = str(uuid.uuid4())
        res_create = self.client.post(
            "/api/v1/orders",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=idemp_key,
            **self.headers
        )
        self.assertEqual(res_create.status_code, 201)
        order_id = res_create.json()["id"]

        # Get Order
        res_get = self.client.get(f"/api/v1/orders/{order_id}", **self.headers)
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()["id"], order_id)

        # Get Order Events
        res_events = self.client.get(f"/api/v1/orders/{order_id}/events", **self.headers)
        self.assertEqual(res_events.status_code, 200)
        self.assertGreaterEqual(len(res_events.json()["results"]), 1)

    def test_order_cancel_lifecycle(self):
        payload = {"instrument": "BTC-USD", "side": "BUY", "order_type": "LIMIT", "quantity": "2", "limit_price": "96.00"}
        res_create = self.client.post(
            "/api/v1/orders",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            **self.headers
        )
        self.assertEqual(res_create.status_code, 201, res_create.json())
        order_id = res_create.json()["id"]
        process_created_order(order_id, "OPEN_THEN_CANCEL")

        res_cancel = self.client.post(f"/api/v1/orders/{order_id}/cancel", **self.headers)
        self.assertEqual(res_cancel.status_code, 200)
        self.assertEqual(res_cancel.json()["state"], OrderState.CANCELED.value)

    def test_executions_endpoint(self):
        res_exec = self.client.get("/api/v1/executions", **self.headers)
        self.assertEqual(res_exec.status_code, 200)
        self.assertIn("results", res_exec.json())
