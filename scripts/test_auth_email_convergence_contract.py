import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "FX/FX/settings.py"
KEYCLOAK_BFF_PATH = ROOT / "FX/users/keycloak_bff.py"
USERS_URLS_PATH = ROOT / "FX/users/urls.py"
EMAIL_CLIENT_PATH = ROOT / "FX/notifications/email_client.py"
INVENTORY_PATH = ROOT / "API_WEBHOOK_INVENTORY.md"


class AuthEmailConvergenceContractTests(unittest.TestCase):
    def setUp(self):
        self.settings = SETTINGS_PATH.read_text(encoding="utf-8")
        self.keycloak_bff = KEYCLOAK_BFF_PATH.read_text(encoding="utf-8")
        self.users_urls = USERS_URLS_PATH.read_text(encoding="utf-8")
        self.email_client = EMAIL_CLIENT_PATH.read_text(encoding="utf-8")
        self.inventory = INVENTORY_PATH.read_text(encoding="utf-8")

    def test_settings_keep_keycloak_as_the_only_human_authority_at_cutover(self):
        self.assertIn("KEYCLOAK_IDENTITY_ENABLED", self.settings)
        self.assertIn("LOCAL_PASSWORD_AUTH_ENABLED", self.settings)
        self.assertIn("EMAIL_REGISTRATION_ENABLED", self.settings)
        self.assertIn("Disable local password authentication and email registration before enabling Keycloak", self.settings)
        self.assertIn("TRANSACTIONAL_EMAIL_ENABLED", self.settings)

    def test_keycloak_bff_and_urls_keep_same_origin_http_only_contract(self):
        self.assertIn("def _set_session_cookies", self.keycloak_bff)
        self.assertIn("def _clear_session_cookies", self.keycloak_bff)
        self.assertIn("KeycloakCallbackView", self.keycloak_bff)
        self.assertIn("KeycloakLogoutView", self.keycloak_bff)
        self.assertIn("stable 503 contract", self.users_urls)
        self.assertIn('path("oidc/login/"', self.users_urls)
        self.assertIn('if settings.LOCAL_PASSWORD_AUTH_ENABLED:', self.users_urls)

    def test_transactional_email_boundary_keeps_secret_file_and_identity_guard(self):
        self.assertIn("BEYVRA_EMAIL_CLIENT_SECRET_FILE", self.email_client)
        self.assertIn("IDENTITY_MAIL_MUST_USE_KEYCLOAK", self.email_client)
        self.assertIn("transactional_email", self.email_client)
        self.assertIn("## Klyrow email and callback boundary", self.inventory)


if __name__ == "__main__":
    unittest.main()
