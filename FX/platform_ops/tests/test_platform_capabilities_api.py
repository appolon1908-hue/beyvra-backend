import uuid
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import exceptions
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

    @override_settings(LIVE_TRADING_ENABLED=True)
    def test_get_platform_config_uses_live_flag_for_product_mode(self):
        response = self.client.get("/api/v1/platform/config")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["live_trading_enabled"])
        self.assertEqual(response.json()["product_mode"], "HYBRID")

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
    @patch("platform_ops.platform_api._optional_user")
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
        optional_user,
        _system_state,
        _latest,
    ):
        optional_user.return_value = self.operator
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
    @patch("platform_ops.platform_api._optional_user")
    def test_get_platform_capabilities_etag_handles_datetime_provider_health(
        self,
        optional_user,
        _system_state,
        _latest,
        _compliance_summary,
    ):
        optional_user.return_value = self.operator
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
    @patch("platform_ops.platform_api._optional_user")
    def test_get_platform_capabilities_includes_compliance_summary(
        self,
        optional_user,
        _system_state,
        _provider_health_visible,
        _compliance_summary,
    ):
        optional_user.return_value = self.user
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

    @patch("platform_ops.platform_api.HealthAuthority.system_state", return_value="HEALTHY")
    @patch("platform_ops.platform_api._provider_health_visible", return_value=False)
    @patch("platform_ops.platform_api._optional_user")
    @patch("platform_ops.platform_api._resolve_compliance_organization", return_value=None)
    def test_authenticated_capabilities_without_tenant_context_stay_readable(
        self,
        _resolve_compliance_organization,
        optional_user,
        _provider_health_visible,
        _system_state,
    ):
        optional_user.return_value = self.user
        response = self.client.get("/api/v1/platform/capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["compliance"]["requirements"],
            ["IDENTITY_VERIFICATION"],
        )

    @patch("platform_ops.platform_api.HealthAuthority.system_state", return_value="HEALTHY")
    @patch("platform_ops.platform_api._provider_health_visible", return_value=False)
    @patch("platform_ops.platform_api._optional_user")
    @patch("platform_ops.platform_api.tenant_context_for_request")
    @patch("platform_ops.platform_api.ComplianceProfile.objects.filter")
    def test_authenticated_capabilities_use_optional_user_resolution(
        self,
        profile_filter,
        tenant_context_for_request,
        optional_user,
        _provider_health_visible,
        _system_state,
    ):
        optional_user.return_value = self.user
        tenant_context_for_request.return_value = type(
            "TenantContext",
            (),
            {"organization": object()},
        )()
        profile_filter.return_value.first.return_value = None

        response = self.client.get("/api/v1/platform/capabilities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["compliance"]["reason_codes"],
            ["KYC_REQUIRED"],
        )

    @patch(
        "platform_ops.platform_api._resolve_compliance_organization",
        return_value=platform_api._TENANT_SELECTION_REQUIRED,
    )
    def test_compliance_summary_marks_multi_tenant_selection_required(
        self,
        _resolve_compliance_organization,
    ):
        request = type("Request", (), {})()
        user = type("User", (), {"is_authenticated": True})()
        request.user = user
        request.headers = {}

        summary = platform_api._compliance_summary(request, user)

        self.assertEqual(
            summary["reason_codes"],
            ["TENANT_SELECTION_REQUIRED"],
        )
        self.assertEqual(summary["requirements"], [])

    @patch("platform_ops.platform_api.get_trading_eligibility")
    @patch("platform_ops.platform_api.ComplianceProfile.objects.filter")
    @patch("platform_ops.platform_api._resolve_compliance_organization")
    def test_compliance_summary_uses_resolved_organization(
        self,
        resolve_compliance_organization,
        profile_filter,
        get_trading_eligibility,
    ):
        organization = object()
        request = type("Request", (), {})()
        request.user = type("User", (), {"is_authenticated": True})()
        request.headers = {}

        profile = profile_filter.return_value.first.return_value = Mock()
        values_list = Mock(return_value=["IDENTITY_VERIFICATION"])
        filtered_requirements = Mock()
        filtered_requirements.exclude.return_value.values_list = values_list
        profile.requirements.filter.return_value = filtered_requirements
        get_trading_eligibility.return_value = type(
            "Decision",
            (),
            {
                "result": "DENIED",
                "policy_version": "fixture-policy",
                "reason_codes": ("KYC_REQUIRED",),
            },
        )()
        resolve_compliance_organization.return_value = organization

        summary = platform_api._compliance_summary(request, request.user)

        profile_filter.assert_called_once_with(
            user=request.user,
            organization=organization,
        )
        filtered_requirements.exclude.assert_called_once_with(
            status__in=("COMPLETED", "WAIVED")
        )
        self.assertEqual(summary["policy_version"], "fixture-policy")
        self.assertEqual(summary["reason_codes"], ["KYC_REQUIRED"])

    @patch("platform_ops.platform_api.tenant_context_for_request")
    def test_invalid_tenant_header_keeps_permission_error(
        self,
        tenant_context_for_request,
    ):
        request = type("Request", (), {})()
        user = type("User", (), {"is_authenticated": True})()
        request.user = user
        request.headers = {"X-Organization-ID": "not-a-uuid"}
        tenant_context_for_request.side_effect = exceptions.PermissionDenied(
            "invalid organization context"
        )

        with self.assertRaises(exceptions.PermissionDenied):
            platform_api._resolve_compliance_organization(request, user)
