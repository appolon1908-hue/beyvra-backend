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
        REAL_DEPOSITS_ENABLED=False,
        REAL_WITHDRAWALS_ENABLED=False,
        REAL_INTERNAL_TRANSFERS_ENABLED=False,
        EXTERNAL_EXECUTION_ENABLED=False,
        LIVE_BROKER_ROUTING_ENABLED=False,
        FIX_LIVE_SESSION_ENABLED=False,
        PAYMENTS_ENABLED=False,
        TRANSACTIONAL_EMAIL_ENABLED=False,
        WELCOME_EMAIL_ENABLED=False,
        REALTIME_V2_V1_FALLBACK_ENABLED=False,
    )
    @patch(
        "platform_ops.health.api.database_read_only_state",
        return_value=True,
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
    def test_exact_release_identity_and_safety_are_publicly_readable(
        self,
        _database_read_only_state,
    ):
        response = APIClient().get(reverse("system-version"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["immutable_identity_verified"])
        self.assertTrue(payload["deployment_read_only"])
        self.assertTrue(payload["database_read_only_enforced"])
        self.assertTrue(payload["effect_flags_disabled"])
        self.assertTrue(payload["read_only_certified"])
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
                "real_deposits_enabled": False,
                "real_withdrawals_enabled": False,
                "real_internal_transfers_enabled": False,
                "external_execution_enabled": False,
                "live_broker_routing_enabled": False,
                "fix_live_session_enabled": False,
                "payments_enabled": False,
                "transactional_email_enabled": False,
                "welcome_email_enabled": False,
                "legacy_realtime_fallback_enabled": False,
                "deployment_read_only": True,
            },
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    @override_settings(
        RELEASE_SHA="",
        DEPLOYMENT_ENV="local",
        SIMULATED_TRADING_ENABLED=False,
    )
    @patch(
        "platform_ops.health.api.database_read_only_state",
        return_value=False,
    )
    @patch.dict(
        os.environ,
        {
            "BEYVRA_IMAGE_DIGEST": "",
            "DEPLOYMENT_READ_ONLY": "false",
        },
        clear=False,
    )
    def test_missing_identity_is_reported_without_fabrication(
        self,
        _database_read_only_state,
    ):
        response = APIClient().get(reverse("system-version"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["immutable_identity_verified"])
        self.assertFalse(payload["deployment_read_only"])
        self.assertFalse(payload["database_read_only_enforced"])
        self.assertFalse(payload["read_only_certified"])
        self.assertEqual(payload["source_sha"], "unknown")
        self.assertEqual(payload["image_digest"], "unknown")
