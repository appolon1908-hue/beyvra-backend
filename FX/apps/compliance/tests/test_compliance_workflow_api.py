import uuid
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from apps.compliance.models import ComplianceProfile
from apps.compliance.domain import AccountState, AmlState, JurisdictionState, KycState, SanctionsState
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
class ComplianceWorkflowApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email=f"comp-wf-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}",
            password="testpassword"
        )
        self.org = Organization.objects.create(name=f"Org {uuid.uuid4()}")
        OrganizationMembership.objects.create(user=self.user, organization=self.org)
        self.profile = ComplianceProfile.objects.create(
            user=self.user,
            organization=self.org,
            account_state=AccountState.ACTIVE,
            kyc_state=KycState.APPROVED,
            aml_state=AmlState.CLEARED,
            sanctions_state=SanctionsState.CLEAR,
            jurisdiction_state=JurisdictionState.SUPPORTED
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_get_compliance_status(self):
        res = self.client.get("/api/v1/compliance/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["result"], "ALLOWED")
        self.assertIn("policy_version", data)

    def test_post_compliance_acknowledgements(self):
        res = self.client.post(
            "/api/v1/compliance/acknowledgements",
            {"document_id": "terms_2026", "document_version": "v1.0"},
            format="json"
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["status"], "RECORDED")
