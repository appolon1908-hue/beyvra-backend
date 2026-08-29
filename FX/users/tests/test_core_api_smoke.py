from unittest.mock import patch

from django.test import override_settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient, APITestCase

from integrations.models import Organization, OrganizationMembership
from users.models import User


SIMULATION = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
)


@SIMULATION
class CoreApiSmokeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="api-smoke@example.test",
            password="safe-test-password",
            phone_number="+12025550170",
        )

    def test_canonical_api_routes_resolve(self):
        routes = {
            "/api/v1/auth/token/": "canonical_auth:token_obtain_pair",
            "/api/v1/auth/token/refresh/": "canonical_auth:token_refresh",
            "/api/v1/auth/token/logout/": "canonical_auth:token_logout",
            "/api/v1/session": "session_resolve_v1",
            "/api/v1/platform/config": "platform-config",
            "/api/v1/platform/capabilities": "platform-capabilities",
            "/api/v1/system/status": "system-status",
            "/api/v1/system/capabilities": "system-capabilities",
            "/api/v1/realtime/v2/connection-token": "realtime_v2_connection_token",
            "/api/v1/realtime/v2/subscription-token": "realtime_v2_subscription_token",
            "/api/v1/realtime/v2/channel-registry": "realtime_v2_channel_registry",
            "/api/v1/realtime/v2/health": "realtime_v2_health",
        }
        for path, expected_name in routes.items():
            with self.subTest(path=path):
                self.assertEqual(resolve(path).view_name, expected_name)

    def test_public_platform_and_system_endpoints_are_available(self):
        expectations = {
            "/api/v1/platform/config": ("schema_version", "product_mode", "api_version"),
            "/api/v1/platform/capabilities": ("schema_version", "simulation_enabled", "compliance"),
            "/api/v1/system/status": ("system_state", "realtime_state", "maintenance_state"),
            "/api/v1/system/capabilities": ("simulation", "market_data", "real_money"),
        }
        for path, keys in expectations.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                for key in keys:
                    self.assertIn(key, payload)

    def test_cookie_login_session_refresh_and_logout_flow(self):
        client = APIClient(enforce_csrf_checks=True)
        login = client.post(
            reverse("canonical_auth:token_obtain_pair"),
            {"email": self.user.email, "password": "safe-test-password"},
            format="json",
            HTTP_USER_AGENT="api-smoke-browser/1",
            REMOTE_ADDR="192.0.2.70",
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("csrftoken", login.cookies)
        for name in ("beyvra_access", "beyvra_refresh"):
            self.assertIn(name, login.cookies)
            self.assertTrue(login.cookies[name]["httponly"])
        for name in ("access_token", "refresh_token"):
            self.assertEqual(login.cookies[name].value, "session")
            self.assertFalse(login.cookies[name]["httponly"])

        session = client.get("/api/v1/session")
        self.assertEqual(session.status_code, 200)
        session_payload = session.json()
        self.assertEqual(session_payload["state"], "user.ready")
        self.assertEqual(session_payload["portal"], "client")
        self.assertEqual(session_payload["allowedPortals"], ["client"])
        self.assertEqual(session_payload["user"]["role"], "User")

        self.assertEqual(client.post(reverse("canonical_auth:token_refresh"), {}, format="json").status_code, 403)
        refreshed = client.post(
            reverse("canonical_auth:token_refresh"),
            {},
            format="json",
            HTTP_X_CSRFTOKEN=login.cookies["csrftoken"].value,
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertTrue(refreshed.cookies["beyvra_access"]["httponly"])

        logout = client.post(
            reverse("canonical_auth:token_logout"),
            {},
            format="json",
            HTTP_X_CSRFTOKEN=login.cookies["csrftoken"].value,
        )
        self.assertEqual(logout.status_code, 200)
        for name in ("beyvra_access", "beyvra_refresh", "access_token", "refresh_token"):
            self.assertEqual(logout.cookies[name]["max-age"], 0)

    def test_private_api_surfaces_fail_closed_without_session(self):
        expectations = {
            "/api/v1/session": {401, 403},
            "/api/v1/realtime/v2/connection-token": {401, 403},
            "/api/v1/realtime/v2/subscription-token": {401, 403},
            "/api/v1/realtime/v2/channel-registry": {401, 403},
        }
        for path, statuses in expectations.items():
            with self.subTest(path=path):
                if "token" in path:
                    response = self.client.post(path, {}, format="json")
                else:
                    response = self.client.get(path)
                self.assertIn(response.status_code, statuses)

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    @patch.dict(
        "os.environ",
        {
            "REALTIME_V2_ENABLED": "true",
            "REALTIME_V2_STAGING_ENABLED": "true",
            "CENTRIFUGO_ENABLED": "true",
            "NATS_JETSTREAM_ENABLED": "true",
            "CENTRIFUGO_TOKEN_HMAC_SECRET": "token-secret-token-secret-token-secret-1",
        },
    )
    def test_authenticated_realtime_registry_excludes_unpublished_news_channels(self):
        client = APIClient()
        login = client.post(
            reverse("canonical_auth:token_obtain_pair"),
            {"email": self.user.email, "password": "safe-test-password"},
            format="json",
            HTTP_USER_AGENT="api-smoke-browser/2",
            REMOTE_ADDR="192.0.2.71",
        )
        self.assertEqual(login.status_code, 200)

        registry = client.get("/api/v1/realtime/v2/channel-registry")
        self.assertEqual(registry.status_code, 200)
        channels = registry.json()["channels"]
        self.assertIn("market.{symbol}.quote", channels)
        self.assertNotIn("news.{symbol}", channels)
        self.assertNotIn("news.market", channels)
        self.assertNotIn("news.economic", channels)

        denied = client.post(
            "/api/v1/realtime/v2/subscription-token",
            {"channel": "news.market"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

    def test_provider_webhooks_fail_closed_without_trust_inputs(self):
        response = self.client.post(
            "/api/v1/webhooks/executions/alpaca",
            b"{}",
            content_type="application/json",
            HTTP_X_TENANT_REF="11111111-1111-1111-1111-111111111111",
        )
        self.assertIn(response.status_code, {403, 503})

    def test_session_contract_exposes_staff_admin_portal(self):
        admin = User.objects.create_user(
            email="admin-smoke@example.test",
            password="safe-test-password",
            phone_number="+12025550171",
            role="Admin",
            is_staff=True,
        )
        self.client.force_authenticate(admin)

        payload = self.client.get("/api/v1/session").json()
        self.assertEqual(payload["portal"], "admin")
        self.assertEqual(payload["allowedPortals"], ["admin", "contractor", "client"])
        self.assertEqual(payload["roles"], ["Admin"])

    def test_session_contract_exposes_contractor_portal(self):
        contractor = User.objects.create_user(
            email="contractor-smoke@example.test",
            password="safe-test-password",
            phone_number="+12025550172",
            role="Contractor",
        )
        organization = Organization.objects.create(name="Contractor Ops")
        OrganizationMembership.objects.create(
            user=contractor,
            organization=organization,
            role="support_agent",
        )
        self.client.force_authenticate(contractor)

        payload = self.client.get("/api/v1/session").json()
        self.assertEqual(payload["portal"], "contractor")
        self.assertEqual(payload["allowedPortals"], ["contractor", "client"])
        self.assertEqual(payload["roles"], ["Contractor"])
        self.assertEqual(payload["operatorRoles"], ["support_agent"])
