from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from platform_ops.health.models import HealthCheckResult,ServiceDefinition
from platform_ops.incidents.models import OperationalIncident
from platform_ops.reconciliation.models import FullStackReconciliationRun

class PublicApiTests(APITestCase):
    def test_liveness_is_fast_and_dependency_free(self):self.assertEqual(self.client.get("/health").status_code,200)
    @override_settings(NATS_JETSTREAM_ENABLED=True)
    def test_readiness_fails_without_outbox_heartbeat(self):
        cache.delete("health:outbox-worker");self.assertEqual(self.client.get("/ready").status_code,503)
    def test_public_status_is_safe(self):
        response=self.client.get("/api/v1/system/status");self.assertEqual(response.status_code,200);self.assertNotIn("hostname",response.json())
    def test_capabilities_never_advertise_real_money(self):
        body=self.client.get("/api/v1/system/capabilities").json();self.assertFalse(body["real_trading"]);self.assertFalse(body["real_money"])

class OperatorApiTests(APITestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser(email="sre@example.test",password="synthetic-test-only");self.client.force_authenticate(self.user)
    def test_operator_routes_require_authentication(self):
        self.client.force_authenticate(None);self.assertEqual(self.client.get("/api/v1/operator/system/health").status_code,401)
    def test_config_api_never_returns_values(self):
        body=self.client.get("/api/v1/operator/system/configuration").json();self.assertTrue(all("value" not in x and "default_safe" not in x for x in body["configuration"]))
    def test_flags_all_high_risk_false(self):
        body=self.client.get("/api/v1/operator/system/feature-flags").json();self.assertTrue(all(not x["enabled"] for x in body["feature_flags"] if x["risk_class"]=="HIGH"))
    def test_mutation_requires_reason(self):
        self.assertEqual(self.client.post("/api/v1/operator/system/kill-switches/GLOBAL_PLATFORM_HALT/activate",{}).status_code,400)
    def test_incident_invalid_transition_rejected(self):
        x=OperationalIncident.objects.create(severity="SEV2",category="TEST",summary="fixture",source="test",deduplication_key="test")
        headers={"HTTP_IDEMPOTENCY_KEY":"incident-invalid","HTTP_X_REQUEST_ID":"65cbf766-67ac-4f77-868a-cacc105008d3","HTTP_IF_MATCH":"OPEN"}
        self.assertEqual(self.client.post(f"/api/v1/operator/system/incidents/{x.id}/resolve",{"reason_code":"test"},format="json",**headers).status_code,409)
    def test_incident_transition_is_idempotent_and_versioned(self):
        x=OperationalIncident.objects.create(severity="SEV2",category="TEST",summary="fixture",source="test",deduplication_key="idempotent-test")
        headers={"HTTP_IDEMPOTENCY_KEY":"incident-ack","HTTP_X_REQUEST_ID":"65cbf766-67ac-4f77-868a-cacc105008d5","HTTP_IF_MATCH":"OPEN"}
        first=self.client.post(f"/api/v1/operator/system/incidents/{x.id}/acknowledge",{"reason_code":"operator_ack"},format="json",**headers)
        replay=self.client.post(f"/api/v1/operator/system/incidents/{x.id}/acknowledge",{"reason_code":"operator_ack"},format="json",**headers)
        conflict=self.client.post(f"/api/v1/operator/system/incidents/{x.id}/acknowledge",{"reason_code":"changed"},format="json",**headers)
        self.assertEqual(first.status_code,200);self.assertEqual(replay.json(),first.json());self.assertEqual(conflict.status_code,409)
        self.assertEqual(OperationalIncident.objects.get(pk=x.pk).state,"ACKNOWLEDGED")
    @override_settings(RELEASE_SHA="a"*40)
    def test_reconciliation_never_fabricates_pass_without_sources(self):
        response=self.client.post("/api/v1/operator/system/reconciliation/run",{"reason_code":"fixture"},format="json",HTTP_IDEMPOTENCY_KEY="reconcile-test",HTTP_X_REQUEST_ID="65cbf766-67ac-4f77-868a-cacc105008d4")
        self.assertEqual(response.status_code,503);self.assertEqual(response.json()["reconciliation"]["state"],"INCOMPLETE")
        replay=self.client.post("/api/v1/operator/system/reconciliation/run",{"reason_code":"fixture"},format="json",HTTP_IDEMPOTENCY_KEY="reconcile-test",HTTP_X_REQUEST_ID="65cbf766-67ac-4f77-868a-cacc105008d4")
        self.assertEqual(replay.status_code,503);self.assertEqual(replay.json(),response.json());self.assertEqual(FullStackReconciliationRun.objects.count(),1)
    def test_no_generic_mutation_endpoints(self):
        for p in ("action","admin","toggle"):self.assertEqual(self.client.post(f"/api/v1/operator/system/{p}",{}).status_code,404)
