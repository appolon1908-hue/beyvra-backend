from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from integrations.models import Organization, OrganizationMembership


class DemoFinancialIsolationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="demo-financial-isolation@example.invalid", password="test-pass", phone_number="+12025550181"
        )
        self.organization = Organization.objects.create(name="Demo isolation tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.organization)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("financial_client.client.FinancialServiceClient._request")
    def test_workspace_simulation_account_never_calls_financial_service(self, financial_request):
        response = self.client.get(
            "/api/v1/workspace/bootstrap", HTTP_X_ORGANIZATION_ID=str(self.organization.id)
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["account"]["demoOnly"])
        financial_request.assert_not_called()
