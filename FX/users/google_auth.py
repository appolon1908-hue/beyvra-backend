import base64
import hashlib
import json
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlencode

import jwt
import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.cache import cache
from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from wallet.constants import DEMO_BALANCE, DEMO_WALLET_NAME
from wallet.models import Currency, Wallet

from .models import AuthenticationAuditEvent, ExternalIdentity, LegalDocument, OAuthTransaction, User, UserLegalAcceptance

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fernet() -> Fernet:
    key = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode("ascii")).decode("utf-8")


def allowlisted_return_path(value: str | None) -> str:
    candidate = value or "/platform"
    if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
        return "/platform"
    if any(candidate == allowed or candidate.startswith(f"{allowed}/") for allowed in settings.AUTH_ALLOWED_RETURN_PATHS):
        return candidate
    return "/platform"


def _audit(event_type: str, *, user=None, transaction_id=None, result="success", reason_code="", request=None):
    return AuthenticationAuditEvent.objects.create(
        event_type=event_type,
        user=user,
        provider="google",
        transaction_id=transaction_id,
        result=result,
        reason_code=reason_code,
        source_ip=(request.META.get("REMOTE_ADDR") if request else None),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:1000] if request else ""),
    )


def _active_legal_versions() -> dict[str, str]:
    return {
        "service-agreement": settings.LEGAL_SERVICE_AGREEMENT_VERSION,
        "privacy-policy": settings.LEGAL_PRIVACY_POLICY_VERSION,
        "risk-disclosure": settings.LEGAL_RISK_DISCLOSURE_VERSION,
    }


def _create_demo_wallet(user):
    currency, _ = Currency.objects.get_or_create(name="Đ", defaults={"symbol": "DEMO", "longer_name": "Demo Dollar"})
    Wallet.objects.get_or_create(name=DEMO_WALLET_NAME, user=user, is_real=False, defaults={"currency": currency, "balance": DEMO_BALANCE})


def start_google_transaction(*, action: str, legal_confirmed: bool, return_path: str, request):
    if not settings.GOOGLE_AUTH_ENABLED or not settings.GOOGLE_OIDC_CLIENT_ID or not settings.GOOGLE_OIDC_REDIRECT_URI:
        raise ValueError("GOOGLE_PROVIDER_DISABLED")
    if action not in {"login", "register", "link"}:
        raise ValueError("INVALID_AUTH_ACTION")
    versions = _active_legal_versions()
    if action == "register":
        if not legal_confirmed:
            raise ValueError("LEGAL_ACCEPTANCE_REQUIRED")
        if not all(versions.values()):
            raise ValueError("LEGAL_DOCUMENTS_UNCONFIGURED")
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    transaction_id = uuid.uuid4()
    OAuthTransaction.objects.create(
        transaction_id=transaction_id,
        state_hash=_hash(state),
        nonce_hash=_hash(nonce),
        nonce_encrypted=_encrypt(nonce),
        pkce_verifier_encrypted=_encrypt(verifier),
        intended_action=action,
        legal_confirmation=legal_confirmed,
        legal_document_versions=versions,
        return_path=allowlisted_return_path(return_path),
        expires_at=timezone.now() + timedelta(seconds=settings.GOOGLE_OIDC_TRANSACTION_TTL_SECONDS),
    )
    _audit("google_auth_started", transaction_id=transaction_id, result="accepted", request=request)
    params = {
        "client_id": settings.GOOGLE_OIDC_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OIDC_REDIRECT_URI,
        "response_type": "code",
        "scope": settings.GOOGLE_OIDC_SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{urlencode(params)}", transaction_id


def verify_google_id_token(raw_id_token: str, *, nonce: str) -> dict:
    jwks_client = jwt.PyJWKClient(GOOGLE_JWKS_URL)
    signing_key = jwks_client.get_signing_key_from_jwt(raw_id_token).key
    claims = jwt.decode(raw_id_token, signing_key, algorithms=["RS256"], audience=settings.GOOGLE_OIDC_CLIENT_ID, issuer=list(GOOGLE_ISSUERS))
    if claims.get("nonce") != nonce:
        raise ValueError("OAUTH_NONCE_INVALID")
    if not claims.get("sub") or not claims.get("email") or claims.get("email_verified") is not True:
        raise ValueError("GOOGLE_EMAIL_UNVERIFIED")
    return claims


def _exchange_code(code: str, verifier: str) -> dict:
    response = requests.post(GOOGLE_TOKEN_ENDPOINT, data={
        "code": code,
        "client_id": settings.GOOGLE_OIDC_CLIENT_ID,
        "client_secret": settings.GOOGLE_OIDC_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_OIDC_REDIRECT_URI,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }, timeout=10)
    if not response.ok:
        raise ValueError("GOOGLE_TOKEN_EXCHANGE_FAILED")
    payload = response.json()
    if not payload.get("id_token"):
        raise ValueError("GOOGLE_ID_TOKEN_MISSING")
    return payload


def _redirect(transaction: OAuthTransaction, **params):
    from django.http import HttpResponseRedirect
    query = urlencode(params)
    separator = "&" if "?" in transaction.return_path else "?"
    return HttpResponseRedirect(f"{transaction.return_path}{separator}{query}")


class GoogleStartView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            authorization_url, transaction_id = start_google_transaction(
                action=request.data.get("action", "login"),
                legal_confirmed=bool(request.data.get("legalConfirmed", False)),
                return_path=request.data.get("returnPath"),
                request=request,
            )
            return Response({"authorizationUrl": authorization_url, "transactionId": str(transaction_id), "expiresIn": settings.GOOGLE_OIDC_TRANSACTION_TTL_SECONDS})
        except ValueError as exc:
            return Response({"code": str(exc), "message": "We could not start Google authentication."}, status=status.HTTP_400_BAD_REQUEST if str(exc) != "GOOGLE_PROVIDER_DISABLED" else status.HTTP_503_SERVICE_UNAVAILABLE)


class AuthProvidersView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"google": {"enabled": bool(settings.GOOGLE_AUTH_ENABLED and settings.GOOGLE_OIDC_CLIENT_ID and settings.GOOGLE_OIDC_REDIRECT_URI)}, "apple": {"enabled": False}, "facebook": {"enabled": False}})


class GoogleCallbackView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        state = request.query_params.get("state", "")
        code = request.query_params.get("code", "")
        oauth_transaction = OAuthTransaction.objects.filter(state_hash=_hash(state)).first()
        if not oauth_transaction:
            return Response({"code": "OAUTH_STATE_INVALID", "message": "We could not complete Google authentication."}, status=400)
        try:
            with db_transaction.atomic():
                locked = OAuthTransaction.objects.select_for_update().get(pk=oauth_transaction.pk)
                if locked.consumed_at or locked.expires_at <= timezone.now():
                    _audit("oauth_callback_replayed", transaction_id=locked.transaction_id, result="denied", reason_code="OAUTH_TRANSACTION_EXPIRED", request=request)
                    return _redirect(locked, auth_error="OAUTH_CALLBACK_REPLAYED")
                if not code:
                    return _redirect(locked, auth_error="GOOGLE_AUTH_CANCELLED")
                verifier = _decrypt(locked.pkce_verifier_encrypted)
                token_payload = _exchange_code(code, verifier)
                claims = verify_google_id_token(token_payload["id_token"], nonce=_nonce_from_transaction(locked))
                locked.consumed_at = timezone.now()
                locked.save(update_fields=["consumed_at"])
                user, outcome = _complete_identity(locked, claims, request)
                if outcome == "link_required":
                    return _redirect(locked, auth_error="ACCOUNT_LINK_REQUIRED")
                ticket = secrets.token_urlsafe(32)
                cache.set(f"google-login-ticket:{ticket}", {"user_id": user.pk, "return_path": locked.return_path}, timeout=60)
                _audit("google_auth_succeeded", user=user, transaction_id=locked.transaction_id, request=request)
                return _redirect(locked, google_ticket=ticket)
        except ValueError as exc:
            _audit("google_auth_failed", transaction_id=oauth_transaction.transaction_id, result="denied", reason_code=str(exc), request=request)
            return _redirect(oauth_transaction, auth_error=str(exc))
        except Exception:
            _audit("google_auth_failed", transaction_id=oauth_transaction.transaction_id, result="denied", reason_code="GOOGLE_AUTH_FAILED", request=request)
            return _redirect(oauth_transaction, auth_error="GOOGLE_AUTH_FAILED")


def _nonce_from_transaction(transaction):
    try:
        nonce = _decrypt(transaction.nonce_encrypted)
    except Exception as exc:
        raise ValueError("OAUTH_NONCE_INVALID") from exc
    if _hash(nonce) != transaction.nonce_hash:
        raise ValueError("OAUTH_NONCE_INVALID")
    return nonce


def _complete_identity(transaction, claims, request):
    subject = claims["sub"]
    email = claims["email"].strip().lower()
    identity = ExternalIdentity.objects.select_related("user").filter(provider="google", provider_subject=subject).first()
    if identity:
        if not identity.user.is_active:
            raise ValueError("ACCOUNT_DISABLED")
        identity.last_authenticated_at = timezone.now()
        identity.save(update_fields=["last_authenticated_at", "updated_at"])
        return identity.user, "login"
    existing = User.objects.filter(email__iexact=email).first()
    if existing:
        _audit("google_identity_link_requested", user=existing, transaction_id=transaction.transaction_id, result="denied", reason_code="ACCOUNT_LINK_REQUIRED", request=request)
        return existing, "link_required"
    if transaction.intended_action == "login" or not settings.GOOGLE_AUTO_CREATE_USERS:
        raise ValueError("ACCOUNT_LINK_REQUIRED")
    with db_transaction.atomic():
        user = User.objects.create_user(email=email, first_name=(claims.get("given_name") or claims.get("name") or "Google")[:20], last_name=(claims.get("family_name") or "User")[:20], phone_number=None, password=secrets.token_urlsafe(32), email_verified=True, email_verified_at=timezone.now(), email_verification_source="google_oidc", is_walkthrough=True)
        ExternalIdentity.objects.create(user=user, provider="google", provider_subject=subject, provider_email=email, provider_email_verified=True, display_name=claims.get("name", "")[:255], profile_picture_url=claims.get("picture", ""), last_authenticated_at=timezone.now())
        for doc_type, version in transaction.legal_document_versions.items():
            document, _ = LegalDocument.objects.get_or_create(document_type=doc_type, version=version, locale="en-US", defaults={"is_active": True})
            UserLegalAcceptance.objects.create(user=user, document=document, accepted_at=timezone.now(), acceptance_source="google-registration", authentication_transaction_id=str(transaction.transaction_id), ip_address=request.META.get("REMOTE_ADDR"), user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000])
        _create_demo_wallet(user)
        _audit("google_registration_created", user=user, transaction_id=transaction.transaction_id, request=request)
    return user, "registered"


class GoogleCredentialView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ticket = request.data.get("ticket", "")
        if not ticket or not cache.add(f"google-login-ticket-used:{ticket}", 1, timeout=300):
            return Response({"code": "GOOGLE_TICKET_REPLAYED", "message": "We could not complete Google authentication."}, status=400)
        payload = cache.get(f"google-login-ticket:{ticket}")
        cache.delete(f"google-login-ticket:{ticket}")
        if not payload:
            return Response({"code": "GOOGLE_TICKET_EXPIRED", "message": "We could not complete Google authentication."}, status=400)
        user = User.objects.filter(pk=payload["user_id"], is_active=True).first()
        if not user:
            return Response({"code": "ACCOUNT_DISABLED", "message": "We could not complete Google authentication."}, status=403)
        refresh = TokenObtainPairSerializer.get_token(user)
        _audit("session_created", user=user, result="success", request=request)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh), "user": {"id": user.pk, "email": user.email, "is_walkthrough": user.is_walkthrough}})
