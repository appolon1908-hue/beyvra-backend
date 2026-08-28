import uuid
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from users.models import User
from integrations.models import Organization, OrganizationMembership


SIMULATION = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
)


@SIMULATION
class RealtimeV1ContractTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email=f"rt-test-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}",
            password="testpassword"
        )
        self.org = Organization.objects.create(name=f"Org {uuid.uuid4()}")
        OrganizationMembership.objects.create(user=self.user, organization=self.org)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_post_realtime_ticket(self):
        res = self.client.post("/api/v1/realtime/ticket")
        self.assertEqual(res.status_code, 201)
        self.assertIn("ticket", res.json())
        self.assertEqual(res.json()["user_id"], str(self.user.pk))

    def test_get_realtime_snapshot(self):
        res = self.client.get("/api/v1/realtime/snapshot?topic=orders")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["topic"], "orders")

    def test_get_realtime_resume_large_gap(self):
        res = self.client.get("/api/v1/realtime/resume?after_sequence=1")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "SNAPSHOT_REQUIRED")
