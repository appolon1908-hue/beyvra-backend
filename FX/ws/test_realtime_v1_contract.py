import uuid
from django.test import TestCase, override_settings
from django.core.cache import cache
from rest_framework.test import APIClient
from users.models import User
from integrations.models import Organization, OrganizationMembership
from ws.recovery import append_event


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
        cached = cache.get(res.json()["ticket"])
        self.assertEqual(cached["user_id"], self.user.pk)
        self.assertEqual(cached["tenant_id"], str(self.org.pk))
        self.assertEqual(res.json()["expires_in_seconds"], 60)

    def test_get_realtime_snapshot(self):
        stored = append_event(
            tenant_ref=str(self.org.pk),
            channel="demo.order",
            event_type="demo.order.updated.v1",
            source="test",
            data={"state": "ACCEPTED"},
        )

        res = self.client.get("/api/v1/realtime/snapshot?topic=orders")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["topic"], "demo.order")
        self.assertEqual(res.json()["as_of_sequence"], stored.sequence)
        self.assertEqual(res.json()["data"], {"state": "ACCEPTED"})

    def test_get_realtime_resume_returns_retained_messages(self):
        append_event(
            tenant_ref=str(self.org.pk),
            channel="demo.order",
            event_type="demo.order.updated.v1",
            source="test",
            data={"state": "ACCEPTED"},
        )
        append_event(
            tenant_ref=str(self.org.pk),
            channel="demo.order",
            event_type="demo.order.updated.v1",
            source="test",
            data={"state": "WORKING"},
        )

        res = self.client.get("/api/v1/realtime/resume?topic=orders&after_sequence=1")
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload["current_sequence"], 2)
        self.assertEqual([message["sequence"] for message in payload["messages"]], [2])
        self.assertEqual(payload["messages"][0]["data"], {"state": "WORKING"})

    def test_realtime_append_suppresses_duplicate_payloads(self):
        first = append_event(
            tenant_ref=str(self.org.pk),
            channel="demo.order",
            event_type="demo.order.updated.v1",
            source="test",
            data={"state": "ACCEPTED"},
        )
        duplicate = append_event(
            tenant_ref=str(self.org.pk),
            channel="demo.order",
            event_type="demo.order.updated.v1",
            source="test",
            data={"state": "ACCEPTED"},
        )
        self.assertEqual(first.sequence, duplicate.sequence)
        self.assertEqual(first.event_id, duplicate.event_id)

    def test_get_realtime_resume_large_gap(self):
        for index in range(102):
            append_event(
                tenant_ref=str(self.org.pk),
                channel="demo.order",
                event_type="demo.order.updated.v1",
                source="test",
                data={"state": f"STATE_{index}"},
            )
        res = self.client.get("/api/v1/realtime/resume?after_sequence=1")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["error"]["code"], "SNAPSHOT_REQUIRED")
        self.assertEqual(res.json()["error"]["current_sequence"], 102)
