from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from platform_ops.health.models import HealthCheckResult,ServiceDefinition
from platform_ops.incidents.models import OperationalIncident
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

class PublicApiTests(APITestCase):
    def test_liveness_is_fast_and_dependency_free(self):self.assertEqual(self.client.get("/health").status_code,200)
    @override_settings(NATS_JETSTREAM_ENABLED=True)
    def test_readiness_fails_without_outbox_heartbeat(self):
        cache.delete("health:outbox-worker");self.assertEqual(self.client.get("/ready").status_code,503)
    @override_settings(READINESS_ENFORCE_IDENTITY_EMAIL=True,EMAIL_REGISTRATION_ENABLED=True,TRANSACTIONAL_EMAIL_ENABLED=False,KEYCLOAK_IDENTITY_ENABLED=False)
    def test_readiness_fails_when_email_delivery_required_but_disabled(self):
        response=self.client.get("/ready")
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()["checks"]["email_delivery"]["reason"],"TRANSACTIONAL_EMAIL_DISABLED")
    @override_settings(READINESS_ENFORCE_IDENTITY_EMAIL=True,EMAIL_REGISTRATION_ENABLED=True,TRANSACTIONAL_EMAIL_ENABLED=True,KEYCLOAK_IDENTITY_ENABLED=False,BEYVRA_EMAIL_API_URL="https://api.example.test",BEYVRA_EMAIL_TOKEN_URL="https://auth.example.test/token",BEYVRA_FROM_DOMAIN="beyvra.com",KLYROW_SMTP_CONNECTIVITY="PASS",STARTTLS="PASS",SPF="PASS",DKIM="PASS",DMARC="PASS",DIRECT_APP_SMTP_ACCESS="BLOCKED",DIRECT_APP_KLYROW_ACCESS="BLOCKED",PLAINTEXT_SMTP_SECRET_IN_GIT="BLOCKED")
    def test_readiness_accepts_configured_local_identity_and_email_secret(self):
        with TemporaryDirectory() as folder:
            secret=Path(folder)/"email-client-secret"; secret.write_text("secret",encoding="utf-8")
            with override_settings(BEYVRA_EMAIL_CLIENT_SECRET_FILE=str(secret)):
                response=self.client.get("/ready")
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()["checks"]["email_delivery"]["ok"])
        self.assertEqual(response.json()["checks"]["identity_provider"]["reason"],"LOCAL_AUTHORITY")
        self.assertTrue(response.json()["checks"]["beyvra_mail_domain"]["ok"])
    @override_settings(READINESS_ENFORCE_IDENTITY_EMAIL=True,EMAIL_REGISTRATION_ENABLED=False,TRANSACTIONAL_EMAIL_ENABLED=False,KEYCLOAK_IDENTITY_ENABLED=False,BEYVRA_FROM_DOMAIN="beyvra.com",KLYROW_SMTP_CONNECTIVITY="PASS",STARTTLS="PASS",SPF="PASS",DKIM="PASS",DMARC="FAIL",DIRECT_APP_SMTP_ACCESS="BLOCKED",DIRECT_APP_KLYROW_ACCESS="BLOCKED",PLAINTEXT_SMTP_SECRET_IN_GIT="BLOCKED")
    def test_readiness_fails_when_beyvra_mail_domain_evidence_is_incomplete(self):
        response=self.client.get("/ready")
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()["checks"]["beyvra_mail_domain"]["reason"],"DMARC_NOT_VERIFIED")
    @override_settings(
        READINESS_ENFORCE_IDENTITY_EMAIL=True,
        READINESS_COLLECT_LIVE_IDENTITY_EMAIL_EVIDENCE=True,
        EMAIL_REGISTRATION_ENABLED=False,
        WELCOME_EMAIL_ENABLED=True,
        TRANSACTIONAL_EMAIL_ENABLED=True,
        KEYCLOAK_IDENTITY_ENABLED=True,
        KEYCLOAK_REGISTRATION_ENABLED="PASS",
        KEYCLOAK_RESET_PASSWORD_ENABLED="PASS",
        KEYCLOAK_EMAIL_VERIFICATION="PASS",
        LOCAL_PASSWORD_AUTH_ENABLED=False,
        KEYCLOAK_ISSUER="https://auth.codestra.co/realms/codestra",
        KEYCLOAK_CLIENT_ID="beyvra-web-production",
        KEYCLOAK_REDIRECT_URI="https://beyvra.com/api/v1/auth/oidc/callback/",
        KEYCLOAK_FRONTEND_CALLBACK="https://beyvra.com/auth/callback",
        KEYCLOAK_POST_LOGOUT_URI="https://beyvra.com/signIn?logged_out=1",
        KEYCLOAK_TOKEN_URI="https://auth.codestra.co/realms/codestra/protocol/openid-connect/token",
        KEYCLOAK_JWKS_URI="https://auth.codestra.co/realms/codestra/protocol/openid-connect/certs",
        BEYVRA_EMAIL_API_URL="https://api.codestra.co",
        BEYVRA_EMAIL_TOKEN_URL="https://auth.codestra.co/realms/codestra/protocol/openid-connect/token",
        BEYVRA_FROM_DOMAIN="beyvra.com",
        KLYROW_SMTP_CONNECTIVITY="PASS",
        STARTTLS="PASS",
        SPF="PASS",
        DKIM="PASS",
        DMARC="PASS",
        DIRECT_APP_SMTP_ACCESS="BLOCKED",
        DIRECT_APP_KLYROW_ACCESS="BLOCKED",
        RESET_TOKEN_OUTSIDE_KEYCLOAK="BLOCKED",
        PLAINTEXT_SMTP_SECRET_IN_GIT="BLOCKED",
    )
    @patch("platform_ops.health.checks.requests.get")
    @patch("notifications.email_client.EmailMiddlewareClient.token",return_value="evidence-token")
    def test_readiness_collects_live_identity_email_evidence_without_secrets(self,token,get):
        get.return_value=Mock(status_code=200,json=Mock(return_value={"keys":[{"kid":"fixture"}]}))
        with TemporaryDirectory() as folder:
            secret=Path(folder)/"email-client-secret"; secret.write_text("secret",encoding="utf-8")
            with override_settings(BEYVRA_EMAIL_CLIENT_SECRET_FILE=str(secret)):
                response=self.client.get("/ready")
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()["checks"]["email_delivery"]["ok"])
        self.assertTrue(response.json()["checks"]["identity_provider"]["ok"])
        self.assertTrue(response.json()["checks"]["beyvra_mail_domain"]["ok"])
        token.assert_called_once()
        get.assert_called_once()
        self.assertNotIn("secret",str(response.json()).lower())
    @override_settings(READINESS_ENFORCE_IDENTITY_EMAIL=False,KEYCLOAK_IDENTITY_ENABLED=False,EMAIL_REGISTRATION_ENABLED=False,TRANSACTIONAL_EMAIL_ENABLED=False)
    def test_identity_email_evidence_command_outputs_safe_json(self):
        output=StringIO()
        call_command("collect_identity_email_readiness_evidence",stdout=output)
        payload=json.loads(output.getvalue())
        self.assertIn("email_delivery",payload["checks"])
        self.assertIn("identity_provider",payload["checks"])
        self.assertNotIn("secret",output.getvalue().lower())
    def test_public_status_is_safe(self):
        response=self.client.get("/api/v1/system/status");self.assertEqual(response.status_code,200);self.assertNotIn("hostname",response.json())
    def test_capabilities_never_advertise_real_money(self):
        body=self.client.get("/api/v1/system/capabilities").json();self.assertFalse(body["real_trading"]);self.assertFalse(body["real_money"])

class OperatorApiTests(APITestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser(email="sre@example.test",password="synthetic-test-only");self.client.force_authenticate(self.user)
    def test_operator_routes_require_authentication(self):
        self.client.force_authenticate(None);self.assertEqual(self.client.get("/api/v1/operator/system/health").status_code,401)
    def test_config_api_never_returns_values(self):
        body=self.client.get("/api/v1/operator/system/configuration").json();self.assertTrue(all("value" not in x and "default_safe" not in x for x in body["configuration"]))
    def test_flags_all_high_risk_false(self):
        body=self.client.get("/api/v1/operator/system/feature-flags").json();self.assertTrue(all(not x["enabled"] for x in body["feature_flags"] if x["risk_class"]=="HIGH"))
    def test_mutation_requires_reason(self):
        self.assertEqual(self.client.post("/api/v1/operator/system/kill-switches/GLOBAL_PLATFORM_HALT/activate",{}).status_code,400)
    def test_incident_invalid_transition_rejected(self):
        x=OperationalIncident.objects.create(severity="SEV2",category="TEST",summary="fixture",source="test",deduplication_key="test")
        self.assertEqual(self.client.post(f"/api/v1/operator/system/incidents/{x.id}/resolve",{"reason_code":"test"}).status_code,409)
    @override_settings(RELEASE_SHA="a"*40)
    def test_reconciliation_never_fabricates_pass_without_sources(self):
        response=self.client.post("/api/v1/operator/system/reconciliation/run",{"reason_code":"fixture"},format="json")
        self.assertEqual(response.status_code,503);self.assertEqual(response.json()["reconciliation"]["state"],"INCOMPLETE")
    def test_no_generic_mutation_endpoints(self):
        for p in ("action","admin","toggle"):self.assertEqual(self.client.post(f"/api/v1/operator/system/{p}",{}).status_code,404)
