import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APISimpleTestCase

SIMULATION = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    LIVE_TRADING_ENABLED=False,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
)


@SIMULATION
class PlatformCapabilitiesApiTests(APISimpleTestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model(
            email=f"platform-user-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}",
        )
        self.operator = user_model(
            email=f"platform-operator-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1203{uuid.uuid4().int % 10000000:07d}",
            is_staff=True,
            is_superuser=True,
        )

    def test_get_platform_config_unauthenticated(self):
        response = self.client.get("/api/v1/platform/config")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["schema_version"], "1.0")
        self.assertTrue(response.json()["simulation_enabled"])
        self.assertFalse(response.json()["live_trading_enabled"])
        self.assertFalse(response.json()["real_money_enabled"])
        self.assertIn("ETag", response)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_get_platform_config_etag_if_none_match(self):
        first = self.client.get("/api/v1/platform/config")
        second = self.client.get(
            "/api/v1/platform/config",
            HTTP_IF_NONE_MATCH=first["ETag"],
        )
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second["ETag"], first["ETag"])

    @patch("platform_ops.platform_api.HealthAuthority.system_state", return_value="HEALTHY")
    def test_get_platform_capabilities_unauthenticated(self, _system_state):
        response = self.client.get("/api/v1/platform/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["simulation_enabled"])
        self.assertFalse(body["live_trading_enabled"])
        self.assertFalse(body["provider_health_visible"])
        self.assertNotIn("provider_health", body)
        self.assertFalse(body["deposits"]["available"])
        self.assertEqual(body["deposits"]["reason_code"], "FEATURE_DISABLED")

    @patch("platform_ops.platform_api.HealthAuthority.latest", return_value=[])
    @patch("platform_ops.platform_api.HealthAuthority.system_state", return_value="HEALTHY")
    @patch(
        "platform_ops.platform_api._compliance_summary",
        return_value={
            "trading_eligible": False,
            "policy_version": "fixture-policy",
            "reason_codes": [],
            "requirements": [],
        },
    )
    def test_get_platform_capabilities_operator_sees_provider_health(
        self,
        _compliance_summary,
        _system_state,
        _latest,
    ):
        self.client.force_authenticate(self.operator)
        response = self.client.get("/api/v1/platform/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["provider_health_visible"])
        self.assertIn("provider_health", response.json())

    @patch(
        "platform_ops.platform_api._compliance_summary",
        return_value={
            "trading_eligible": False,
            "policy_version": "fixture-policy",
            "reason_codes": ["KYC_REQUIRED"],
            "requirements": ["IDENTITY_VERIFICATION"],
        },
    )
    @patch("platform_ops.platform_api._provider_health_visible", return_value=False)
    @patch("platform_ops.platform_api.HealthAuthority.system_state", return_value="HEALTHY")
    def test_get_platform_capabilities_includes_compliance_summary(
        self,
        _system_state,
        _provider_health_visible,
        _compliance_summary,
    ):
        self.client.force_authenticate(self.user)
        body = self.client.get("/api/v1/platform/capabilities").json()
        self.assertFalse(body["compliance"]["trading_eligible"])
        self.assertEqual(body["compliance"]["policy_version"], "fixture-policy")
        self.assertEqual(body["compliance"]["reason_codes"], ["KYC_REQUIRED"])
        self.assertEqual(
            body["compliance"]["requirements"],
            ["IDENTITY_VERIFICATION"],
        )
