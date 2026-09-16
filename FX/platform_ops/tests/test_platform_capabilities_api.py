import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APISimpleTestCase

from platform_ops import platform_api

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
            "reason_codes": [],
            "requirements": [],
        },
    )
    @patch(
        "platform_ops.platform_api.HealthAuthority.latest",
        return_value=[
            {
                "service": "market-data",
                "criticality": "TIER_1",
                "health": "HEALTHY",
                "latency_ms": "12",
                "observed_at": timezone.now(),
                "failure_reason_safe": "NOT_OBSERVED",
            }
        ],
    )
    @patch("platform_ops.platform_api.HealthAuthority.system_state", return_value="HEALTHY")
    def test_get_platform_capabilities_etag_handles_datetime_provider_health(
        self,
        _system_state,
        _latest,
        _compliance_summary,
    ):
        self.client.force_authenticate(self.operator)
        response = self.client.get("/api/v1/platform/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ETag", response)

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

    @patch("platform_ops.platform_api.OrganizationMembership.objects.filter")
    def test_provider_health_visibility_requires_active_membership(
        self,
        membership_filter,
    ):
        membership_filter.return_value.exists.return_value = True
        user = get_user_model()(
            email=f"sre-user-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1204{uuid.uuid4().int % 10000000:07d}",
        )

        self.assertTrue(platform_api._provider_health_visible(user))
        membership_filter.assert_called_once_with(
            user=user,
            role__in=platform_api.SRE_ROLES,
            is_active=True,
            organization__is_active=True,
        )

    @patch("platform_ops.platform_api.get_trading_eligibility")
    @patch("platform_ops.platform_api.ComplianceProfile.objects.filter")
    @patch("platform_ops.platform_api.organization_for_request")
    def test_compliance_summary_uses_resolved_organization(
        self,
        organization_for_request,
        profile_filter,
        get_trading_eligibility,
    ):
        organization = object()
        request = type("Request", (), {})()
        request.user = type("User", (), {"is_authenticated": True})()
        request.headers = {}

        profile = profile_filter.return_value.first.return_value = type(
            "Profile",
            (),
            {},
        )()
        profile.requirements = type("Requirements", (), {})()
        profile.requirements.filter = lambda **_kwargs: type(
            "RequirementSet",
            (),
            {
                "exclude": lambda self, **_exclude: type(
                    "ValueList",
                    (),
                    {
                        "values_list": lambda self, *_args, **_kwargs: [
                            "IDENTITY_VERIFICATION"
                        ]
                    },
                )()
            },
        )()
        get_trading_eligibility.return_value = type(
            "Decision",
            (),
            {
                "result": "DENIED",
                "policy_version": "fixture-policy",
                "reason_codes": ("KYC_REQUIRED",),
            },
        )()
        organization_for_request.return_value = organization

        summary = platform_api._compliance_summary(request)

        profile_filter.assert_called_once_with(
            user=request.user,
            organization=organization,
        )
        self.assertEqual(summary["policy_version"], "fixture-policy")
        self.assertEqual(summary["reason_codes"], ["KYC_REQUIRED"])
