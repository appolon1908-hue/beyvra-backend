"""Keycloak Authorization Code + PKCE boundary for Beyvra's browser client.

Keycloak is the only human password and recovery authority.  Beyvra exchanges
the authorization code server-side and exposes only its existing, bound,
HttpOnly session cookies to the browser.
"""

import base64
import hashlib
import re
import secrets
from urllib.parse import urlencode

import jwt
import requests
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from apps.foundation.services import enqueue_event
from operations.services import issue_session_token_pair, revoke_bound_session
from users.email_verification import queue_email
from users.models import User


TRANSACTION_PREFIX = "beyvra:oidc:transaction:"
SESSION_PREFIX = "beyvra:oidc:session:"
ROLE_MAP = {
    "beyvra-super-admin": ("Super Admin", True, True),
    "beyvra-admin": ("Admin", True, False),
    "beyvra-user": ("User", False, False),
}


def _enabled():
    return bool(getattr(settings, "KEYCLOAK_IDENTITY_ENABLED", False))


def _unavailable():
    return Response(
        {"code": "IDENTITY_PROVIDER_UNAVAILABLE", "message": "Sign-in is temporarily unavailable."},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _safe_return_path(value):
    candidate = str(value or "/platform")
    return candidate if candidate in settings.AUTH_ALLOWED_RETURN_PATHS else "/platform"


def _pkce_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _start_authorization(request, *, registration=False, action=None):
    if not _enabled():
        return _unavailable()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    transaction_data = {
        "nonce": nonce,
        "verifier": verifier,
        "next_path": _safe_return_path(request.query_params.get("next")),
    }
    cache.set(
        f"{TRANSACTION_PREFIX}{state}",
        transaction_data,
        timeout=settings.KEYCLOAK_TRANSACTION_TTL_SECONDS,
    )
    params = {
        "client_id": settings.KEYCLOAK_CLIENT_ID,
        "redirect_uri": settings.KEYCLOAK_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if action:
        params["kc_action"] = action
    endpoint = "registrations" if registration else "auth"
    return HttpResponseRedirect(f"{settings.KEYCLOAK_ISSUER}/protocol/openid-connect/{endpoint}?{urlencode(params)}")


def _clean_name(value, fallback):
    cleaned = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ' -]", "", str(value or "")).strip()
    return (cleaned or fallback)[:20]


def _role_from_claims(claims):
    roles = set((claims.get("realm_access") or {}).get("roles") or [])
    resource_roles = ((claims.get("resource_access") or {}).get(settings.KEYCLOAK_CLIENT_ID) or {}).get("roles") or []
    roles.update(resource_roles)
    for key in ("beyvra-super-admin", "beyvra-admin", "beyvra-user"):
        if key in roles:
            return ROLE_MAP[key]
    return ROLE_MAP["beyvra-user"]


def _identity_reference(issuer, subject):
    return hashlib.sha256(f"{issuer}|{subject}".encode()).hexdigest()


def _bind_user(claims):
    issuer = claims["iss"]
    subject = claims["sub"]
    email = claims["email"].strip().lower()
    role, is_staff, is_superuser = _role_from_claims(claims)
    now = timezone.now()
    created = False

    with transaction.atomic():
        user = User.objects.select_for_update().filter(
            identity_issuer=issuer, identity_subject=subject
        ).first()
        if user is None:
            user = User.objects.select_for_update().filter(email__iexact=email).first()
            if user and user.identity_subject and (
                user.identity_issuer != issuer or user.identity_subject != subject
            ):
                raise PermissionError("IDENTITY_BINDING_CONFLICT")
            if user is None:
                user = User(
                    email=email,
                    first_name=_clean_name(claims.get("given_name"), "Beyvra"),
                    last_name=_clean_name(claims.get("family_name"), "User"),
                    is_active=True,
                    is_walkthrough=True,
                )
                created = True
            user.identity_issuer = issuer
            user.identity_subject = subject

        if user.email.lower() != email:
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                raise PermissionError("IDENTITY_EMAIL_CONFLICT")
            user.email = email
        user.first_name = _clean_name(claims.get("given_name"), user.first_name or "Beyvra")
        user.last_name = _clean_name(claims.get("family_name"), user.last_name or "User")
        user.email_verified = True
        user.email_verified_at = user.email_verified_at or now
        user.email_verification_source = "keycloak"
        user.role = role
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.set_unusable_password()
        try:
            user.save()
        except IntegrityError as exc:
            raise PermissionError("IDENTITY_BINDING_CONFLICT") from exc

        if created:
            enqueue_event(
                aggregate_type="identity_account",
                aggregate_id=user.pk,
                event_type="identity.account.provisioned",
                tenant_ref="beyvra",
                payload={
                    "identity_ref": _identity_reference(issuer, subject),
                    "local_user_ref": str(user.pk),
                    "roles": [role],
                    "authority": "keycloak",
                },
            )
            if getattr(settings, "WELCOME_EMAIL_ENABLED", False):
                queue_email(
                    event_type="user.registration.completed",
                    email=user.email,
                    template_key="welcome_email",
                    payload={"display_name": user.first_name, "frontend_url": settings.PUBLIC_SITE_URL},
                    idempotency_key=f"welcome:{user.pk}:keycloak",
                    user_id=user.pk,
                    account_id=user.pk,
                )
    return user


def _validate_id_token(token, nonce):
    jwks = jwt.PyJWKClient(settings.KEYCLOAK_JWKS_URI, cache_keys=True, lifespan=300)
    signing_key = jwks.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.KEYCLOAK_CLIENT_ID,
        issuer=settings.KEYCLOAK_ISSUER,
        options={"require": ["exp", "iat", "iss", "sub", "aud", "nonce", "email", "email_verified"]},
    )
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise jwt.InvalidTokenError("nonce mismatch")
    if claims.get("email_verified") is not True:
        raise jwt.InvalidTokenError("email is not verified")
    return claims


def _set_session_cookies(response, request, credentials, id_token):
    cookie_options = {"secure": True, "httponly": True, "samesite": "Strict", "path": "/"}
    response.set_cookie("beyvra_access", credentials["access"], **cookie_options)
    response.set_cookie("beyvra_refresh", credentials["refresh"], **cookie_options)
    handle = secrets.token_urlsafe(32)
    cache.set(
        f"{SESSION_PREFIX}{handle}",
        {"id_token": id_token, "user_id": credentials["session"].account_id},
        timeout=settings.KEYCLOAK_SESSION_HINT_TTL_SECONDS,
    )
    response.set_cookie("beyvra_oidc_session", handle, **cookie_options)
    response.set_cookie("csrftoken", get_token(request), secure=True, httponly=False, samesite="Strict", path="/")


def _clear_session_cookies(response):
    for name in ("beyvra_access", "beyvra_refresh", "beyvra_oidc_session", "csrftoken"):
        response.delete_cookie(name, path="/", samesite="Strict")


class KeycloakLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return _start_authorization(request)


class KeycloakRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return _start_authorization(request, registration=True)


class KeycloakPasswordResetView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # Keycloak owns the generic account lookup, reset token, and SECURITY mail.
        return _start_authorization(request, action="UPDATE_PASSWORD")


class KeycloakCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        if not _enabled():
            return _unavailable()
        state = str(request.query_params.get("state", ""))
        if len(state) > 200:
            return Response({"code": "INVALID_AUTH_TRANSACTION"}, status=status.HTTP_400_BAD_REQUEST)
        transaction_data = cache.get(f"{TRANSACTION_PREFIX}{state}") if state else None
        if not transaction_data:
            return Response({"code": "INVALID_AUTH_TRANSACTION"}, status=status.HTTP_400_BAD_REQUEST)
        cache.delete(f"{TRANSACTION_PREFIX}{state}")
        if request.query_params.get("error") or not request.query_params.get("code"):
            return HttpResponseRedirect(f"{settings.KEYCLOAK_FRONTEND_CALLBACK}?error=authentication_cancelled")
        try:
            token_response = requests.post(
                settings.KEYCLOAK_TOKEN_URI,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.KEYCLOAK_CLIENT_ID,
                    "redirect_uri": settings.KEYCLOAK_REDIRECT_URI,
                    "code": request.query_params["code"],
                    "code_verifier": transaction_data["verifier"],
                },
                timeout=(3.05, 8),
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            id_token = token_payload["id_token"]
            claims = _validate_id_token(id_token, transaction_data["nonce"])
            user = _bind_user(claims)
            if not user.is_active:
                raise PermissionError("ACCOUNT_DISABLED")
            credentials = issue_session_token_pair(user=user, request=request, mfa_verified=True)
        except (KeyError, TypeError, ValueError, PermissionError, requests.RequestException, jwt.PyJWTError):
            return HttpResponseRedirect(f"{settings.KEYCLOAK_FRONTEND_CALLBACK}?error=authentication_failed")

        query = urlencode({"next": transaction_data["next_path"]})
        response = HttpResponseRedirect(f"{settings.KEYCLOAK_FRONTEND_CALLBACK}?{query}")
        _set_session_cookies(response, request, credentials, id_token)
        return response


class KeycloakCsrfView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        response = Response({"csrfToken": get_token(request)})
        response.set_cookie("csrftoken", get_token(request), secure=True, httponly=False, samesite="Strict", path="/")
        return response


class KeycloakLogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_id = request.auth.get("session_id") if request.auth else None
        if session_id:
            revoke_bound_session(user=request.user, session_id=session_id)
        refresh_value = request.COOKIES.get("beyvra_refresh")
        if refresh_value:
            try:
                RefreshToken(refresh_value).blacklist()
            except TokenError:
                pass

        handle = request.COOKIES.get("beyvra_oidc_session")
        session_hint = cache.get(f"{SESSION_PREFIX}{handle}") if handle else None
        if handle:
            cache.delete(f"{SESSION_PREFIX}{handle}")
        params = {
            "client_id": settings.KEYCLOAK_CLIENT_ID,
            "post_logout_redirect_uri": settings.KEYCLOAK_POST_LOGOUT_URI,
        }
        if session_hint and session_hint.get("id_token"):
            params["id_token_hint"] = session_hint["id_token"]
        logout_url = f"{settings.KEYCLOAK_END_SESSION_URI}?{urlencode(params)}"
        response = Response({"detail": "Logged out", "logoutUrl": logout_url})
        _clear_session_cookies(response)
        return response


class KeycloakConfigView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({
            "enabled": _enabled(),
            "issuer": settings.KEYCLOAK_ISSUER if _enabled() else None,
            "registrationEnabled": _enabled(),
            "passwordResetAuthority": "keycloak" if _enabled() else "local",
        })
