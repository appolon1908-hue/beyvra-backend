import uuid
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
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
)


@SIMULATION
class PlatformCapabilitiesApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email=f"platform-test-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}",
            password="testpassword"
        )
        self.staff_user = User.objects.create_user(
            email=f"platform-staff-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}",
            password="testpassword",
            is_staff=True
        )

    def test_get_platform_config_unauthenticated(self):
        response = self.client.get("/api/v1/platform/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["schema_version"], "1.0")
        self.assertTrue(data["simulation_enabled"])
        self.assertFalse(data["live_trading_enabled"])
        self.assertFalse(data["real_money_enabled"])
        self.assertIn("ETag", response.headers)
        self.assertEqual(response.headers.get("Cache-Control"), "private, no-store")

    def test_get_platform_config_etag_if_none_match(self):
        res1 = self.client.get("/api/v1/platform/config")
        etag = res1.headers["ETag"]
        res2 = self.client.get("/api/v1/platform/config", HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(res2.status_code, 304)

    def test_get_platform_capabilities_unauthenticated(self):
        response = self.client.get("/api/v1/platform/capabilities")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["simulation_enabled"])
        self.assertFalse(data["live_trading_enabled"])
        self.assertFalse(data["provider_health_visible"])
        self.assertNotIn("provider_health", data)
        self.assertFalse(data["deposits"]["available"])
        self.assertEqual(data["deposits"]["reason_code"], "FEATURE_DISABLED")

    def test_get_platform_capabilities_staff_user_sees_provider_health(self):
        self.client.force_authenticate(self.staff_user)
        response = self.client.get("/api/v1/platform/capabilities")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["provider_health_visible"])
        self.assertIn("provider_health", data)

    def test_get_platform_capabilities_compliance_evaluation(self):
        self.client.force_authenticate(self.user)
        res_unapproved = self.client.get("/api/v1/platform/capabilities")
        self.assertFalse(res_unapproved.json()["compliance"]["trading_eligible"])

        # Approve compliance
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
        res_approved = self.client.get("/api/v1/platform/capabilities")
        self.assertTrue(res_approved.json()["compliance"]["trading_eligible"])
