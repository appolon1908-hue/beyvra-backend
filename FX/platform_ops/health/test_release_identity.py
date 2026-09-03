import os
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient


class ReleaseIdentityTests(SimpleTestCase):
    @override_settings(
        RELEASE_SHA="a" * 40,
        DEPLOYMENT_ENV="production",
        SIMULATED_TRADING_ENABLED=False,
        LIVE_TRADING_ENABLED=False,
        REAL_TRADING_ENABLED=False,
        REAL_MONEY_ENABLED=False,
        EXTERNAL_EXECUTION_ENABLED=False,
    )
    @patch.dict(
        os.environ,
        {
            "BEYVRA_IMAGE_DIGEST": (
                "ghcr.io/appolon1908-hue/beyvra-backend@sha256:"
                + ("b" * 64)
            ),
            "BEYVRA_RELEASE_ID": "release-test",
            "BEYVRA_BUILD_TIMESTAMP": "2026-09-03T00:00:00Z",
            "DEPLOYMENT_READ_ONLY": "true",
        },
        clear=False,
    )
    def test_exact_release_identity_and_safety_are_publicly_readable(self):
        response = APIClient().get(reverse("system-version"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["immutable_identity_verified"])
        self.assertTrue(payload["deployment_read_only"])
        self.assertEqual(payload["source_sha"], "a" * 40)
        self.assertEqual(
            payload["image_digest"],
            "ghcr.io/appolon1908-hue/beyvra-backend@sha256:"
            + ("b" * 64),
        )
        self.assertEqual(
            payload["safety"],
            {
                "simulation_enabled": False,
                "live_trading_enabled": False,
                "real_trading_enabled": False,
                "real_money_enabled": False,
                "external_execution_enabled": False,
                "deployment_read_only": True,
            },
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(
        RELEASE_SHA="",
        DEPLOYMENT_ENV="local",
        SIMULATED_TRADING_ENABLED=False,
    )
    @patch.dict(
        os.environ,
        {
            "BEYVRA_IMAGE_DIGEST": "",
            "DEPLOYMENT_READ_ONLY": "false",
        },
        clear=False,
    )
    def test_missing_identity_is_reported_without_fabrication(self):
        response = APIClient().get(reverse("system-version"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["immutable_identity_verified"])
        self.assertFalse(payload["deployment_read_only"])
        self.assertEqual(payload["source_sha"], "unknown")
        self.assertEqual(payload["image_digest"], "unknown")
