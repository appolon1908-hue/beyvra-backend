from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


class PortfolioSummaryTests(TestCase):
    def test_legacy_summary_delegates_to_canonical_portfolio_authority(self):
        user = get_user_model().objects.create_user(
            email="portfolio@example.com", password="test-pass", phone_number="+12025550132"
        )
        anonymous = APIClient().get("/api/portfolio/summary/", secure=True)
        client = APIClient()
        client.force_authenticate(user)
        legacy = client.get("/api/portfolio/summary/", secure=True)
        canonical = client.get("/api/v1/portfolio/summary", secure=True)

        self.assertEqual(anonymous.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(legacy.status_code, status.HTTP_200_OK)
        self.assertEqual(legacy.data["account_id"], canonical.data["account_id"])
        self.assertEqual(legacy.data["equity"], canonical.data["equity"])
        self.assertEqual(legacy.data["valuation_quality"], canonical.data["valuation_quality"])
        self.assertEqual(legacy["Deprecation"], "true")
        self.assertIn("/api/v1/portfolio/", legacy["Link"])
