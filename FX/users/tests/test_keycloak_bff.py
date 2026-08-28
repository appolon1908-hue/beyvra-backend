import re
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import jwt
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.foundation.models import OutboxEvent
from users.models import User


OIDC_SETTINGS = {
    "KEYCLOAK_IDENTITY_ENABLED": True,
    "LOCAL_PASSWORD_AUTH_ENABLED": False,
    "EMAIL_REGISTRATION_ENABLED": False,
    "KEYCLOAK_ISSUER": "https://auth.codestra.co/realms/codestra",
    "KEYCLOAK_CLIENT_ID": "beyvra-web-production",
    "KEYCLOAK_REDIRECT_URI": "https://beyvra.com/api/v1/auth/oidc/callback/",
    "KEYCLOAK_FRONTEND_CALLBACK": "https://beyvra.com/auth/callback",
    "KEYCLOAK_POST_LOGOUT_URI": "https://beyvra.com/signIn?logged_out=1",
    "KEYCLOAK_TOKEN_URI": "https://auth.codestra.co/realms/codestra/protocol/openid-connect/token",
    "KEYCLOAK_JWKS_URI": "https://auth.codestra.co/realms/codestra/protocol/openid-connect/certs",
    "KEYCLOAK_END_SESSION_URI": "https://auth.codestra.co/realms/codestra/protocol/openid-connect/logout",
    "KEYCLOAK_TRANSACTION_TTL_SECONDS": 300,
    "KEYCLOAK_SESSION_HINT_TTL_SECONDS": 3600,
}


@override_settings(**OIDC_SETTINGS)
class KeycloakBffTests(APITestCase):
    def setUp(self):
        cache.clear()

    def _begin(self, path="/api/v1/auth/oidc/login/?next=/platform"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn("code_verifier", query)
        return query

    def _claims(self, query, **updates):
        state = query["state"][0]
        transaction_data = cache.get(f"beyvra:oidc:transaction:{state}")
        claims = {
            "iss": OIDC_SETTINGS["KEYCLOAK_ISSUER"],
            "sub": "kc-user-1",
            "aud": OIDC_SETTINGS["KEYCLOAK_CLIENT_ID"],
            "exp": 4102444800,
            "iat": 1700000000,
            "nonce": transaction_data["nonce"],
            "email": "person@example.com",
            "email_verified": True,
            "given_name": "Test",
            "family_name": "User",
            "realm_access": {"roles": ["beyvra-user"]},
        }
        claims.update(updates)
        return state, claims

    @patch("users.keycloak_bff.issue_session_token_pair")
    @patch("users.keycloak_bff._validate_id_token")
    @patch("users.keycloak_bff.requests.post")
    def test_callback_binds_identity_without_exposing_tokens(self, post, validate, issue):
        query = self._begin()
        state, claims = self._claims(query)
        validate.return_value = claims
        post.return_value = Mock(raise_for_status=Mock(), json=Mock(return_value={"id_token": "keycloak-id-token"}))
        session = Mock(account_id=1)
        issue.return_value = {"access": "local-access", "refresh": "local-refresh", "session": session}

        response = self.client.get(f"/api/v1/auth/oidc/callback/?state={state}&code=one-time-code")

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("token", response["Location"])
        self.assertTrue(response.cookies["beyvra_access"]["httponly"])
        self.assertTrue(response.cookies["beyvra_refresh"]["httponly"])
        self.assertEqual(response.cookies["access_token"].value, "session")
        self.assertEqual(response.cookies["refresh_token"].value, "session")
        self.assertFalse(response.cookies["access_token"]["httponly"])
        self.assertNotIn(".", response.cookies["access_token"].value)
        user = User.objects.get(email="person@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.identity_subject, "kc-user-1")
        event = OutboxEvent.objects.get(event_type="identity.account.provisioned")
        self.assertNotIn("email", event.payload)
        self.assertNotIn("kc-user-1", str(event.payload))

    @patch("users.keycloak_bff.issue_session_token_pair")
    @patch("users.keycloak_bff._validate_id_token")
    @patch("users.keycloak_bff.requests.post")
    def test_admin_role_is_synchronized_from_keycloak(self, post, validate, issue):
        query = self._begin()
        state, claims = self._claims(query, realm_access={"roles": ["beyvra-admin"]})
        validate.return_value = claims
        post.return_value = Mock(raise_for_status=Mock(), json=Mock(return_value={"id_token": "id"}))
        issue.return_value = {"access": "a", "refresh": "r", "session": Mock(account_id=1)}

        self.client.get(f"/api/v1/auth/oidc/callback/?state={state}&code=code")

        user = User.objects.get(email="person@example.com")
        self.assertEqual(user.role, "Admin")
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_state_is_single_use(self):
        query = self._begin()
        state = query["state"][0]
        first = self.client.get(f"/api/v1/auth/oidc/callback/?state={state}&error=access_denied")
        second = self.client.get(f"/api/v1/auth/oidc/callback/?state={state}&code=replay")
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 400)

    def test_invalid_return_path_is_not_reflected(self):
        query = self._begin("/api/v1/auth/oidc/login/?next=https://evil.example/")
        state = query["state"][0]
        self.assertEqual(cache.get(f"beyvra:oidc:transaction:{state}")["next_path"], "/platform")

    def test_protected_deep_link_is_preserved(self):
        query = self._begin("/api/v1/auth/oidc/login/?next=/platform/trades/42")
        state = query["state"][0]
        self.assertEqual(
            cache.get(f"beyvra:oidc:transaction:{state}")["next_path"],
            "/platform/trades/42",
        )

    @patch("users.keycloak_bff.jwt.decode")
    @patch("users.keycloak_bff.jwt.PyJWKClient")
    def test_unverified_email_is_rejected(self, jwks, decode):
        signing_key = Mock(key="key")
        jwks.return_value.get_signing_key_from_jwt.return_value = signing_key
        decode.return_value = {"nonce": "n", "email_verified": False}
        from users.keycloak_bff import _validate_id_token
        with self.assertRaises(jwt.InvalidTokenError):
            _validate_id_token("id-token", "n")

    def test_password_reset_uses_keycloak_action(self):
        response = self.client.get("/api/v1/auth/oidc/password-reset/")
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(query["kc_action"], ["UPDATE_PASSWORD"])
