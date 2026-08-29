import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from .models import HealthCheckResult, ServiceDefinition


def check_postgres():
    start=time.perf_counter()
    try:
        with connection.cursor() as cursor: cursor.execute("SELECT 1"); ok=cursor.fetchone()[0] == 1
        return ok, (time.perf_counter()-start)*1000, ""
    except Exception: return False, (time.perf_counter()-start)*1000, "DEPENDENCY_UNAVAILABLE"


def check_redis():
    start=time.perf_counter()
    try:
        cache.set("ops:health", "1", 5); ok=cache.get("ops:health") == "1"
        return ok, (time.perf_counter()-start)*1000, ""
    except Exception: return False, (time.perf_counter()-start)*1000, "DEPENDENCY_UNAVAILABLE"


def _https_url(value):
    parsed = urlparse(str(value or ""))
    return parsed.scheme == "https" and bool(parsed.netloc)


def _secret_file_present(value):
    try:
        return Path(value).is_file() and bool(Path(value).read_text(encoding="utf-8").strip())
    except (OSError, TypeError, ValueError):
        return False


def check_email_delivery_configuration():
    start = time.perf_counter()
    try:
        if not (settings.EMAIL_REGISTRATION_ENABLED or getattr(settings, "WELCOME_EMAIL_ENABLED", False) or settings.TRANSACTIONAL_EMAIL_ENABLED):
            return True, (time.perf_counter() - start) * 1000, "DISABLED"
        if not settings.TRANSACTIONAL_EMAIL_ENABLED:
            return False, (time.perf_counter() - start) * 1000, "TRANSACTIONAL_EMAIL_DISABLED"
        if not _https_url(settings.BEYVRA_EMAIL_API_URL) or not _https_url(settings.BEYVRA_EMAIL_TOKEN_URL):
            return False, (time.perf_counter() - start) * 1000, "EMAIL_PROVIDER_URL_INVALID"
        if not _secret_file_present(settings.BEYVRA_EMAIL_CLIENT_SECRET_FILE):
            return False, (time.perf_counter() - start) * 1000, "EMAIL_SECRET_FILE_MISSING"
        if settings.READINESS_COLLECT_LIVE_IDENTITY_EMAIL_EVIDENCE:
            from notifications.email_client import EmailMiddlewareClient
            EmailMiddlewareClient().token()
        return True, (time.perf_counter() - start) * 1000, ""
    except Exception:
        return False, (time.perf_counter() - start) * 1000, "EMAIL_PROVIDER_UNAVAILABLE"


def check_identity_provider_configuration():
    start = time.perf_counter()
    try:
        if not settings.KEYCLOAK_IDENTITY_ENABLED:
            return True, (time.perf_counter() - start) * 1000, "LOCAL_AUTHORITY"
        required = (
            settings.KEYCLOAK_ISSUER,
            settings.KEYCLOAK_CLIENT_ID,
            settings.KEYCLOAK_REDIRECT_URI,
            settings.KEYCLOAK_FRONTEND_CALLBACK,
            settings.KEYCLOAK_POST_LOGOUT_URI,
            settings.KEYCLOAK_TOKEN_URI,
            settings.KEYCLOAK_JWKS_URI,
        )
        if not all(required) or not all(_https_url(value) for value in (settings.KEYCLOAK_ISSUER, settings.KEYCLOAK_REDIRECT_URI, settings.KEYCLOAK_FRONTEND_CALLBACK, settings.KEYCLOAK_POST_LOGOUT_URI, settings.KEYCLOAK_TOKEN_URI, settings.KEYCLOAK_JWKS_URI)):
            return False, (time.perf_counter() - start) * 1000, "IDENTITY_PROVIDER_CONFIG_INVALID"
        if settings.LOCAL_PASSWORD_AUTH_ENABLED or settings.EMAIL_REGISTRATION_ENABLED:
            return False, (time.perf_counter() - start) * 1000, "DUAL_CREDENTIAL_AUTHORITY"
        if settings.READINESS_COLLECT_LIVE_IDENTITY_EMAIL_EVIDENCE:
            response = requests.get(settings.KEYCLOAK_JWKS_URI, timeout=5, allow_redirects=False)
            if response.status_code >= 400:
                return False, (time.perf_counter() - start) * 1000, "IDENTITY_DISCOVERY_UNAVAILABLE"
            payload = response.json()
            if not isinstance(payload.get("keys"), list):
                return False, (time.perf_counter() - start) * 1000, "IDENTITY_DISCOVERY_INVALID"
        return True, (time.perf_counter() - start) * 1000, ""
    except Exception:
        return False, (time.perf_counter() - start) * 1000, "IDENTITY_DISCOVERY_UNAVAILABLE"


def identity_email_readiness_checks():
    if not settings.READINESS_ENFORCE_IDENTITY_EMAIL:
        return {
            "email_delivery": {"ok": True, "reason": "NOT_ENFORCED"},
            "identity_provider": {"ok": True, "reason": "NOT_ENFORCED"},
        }
    email_ok, _, email_reason = check_email_delivery_configuration()
    identity_ok, _, identity_reason = check_identity_provider_configuration()
    return {
        "email_delivery": {"ok": email_ok, "reason": email_reason},
        "identity_provider": {"ok": identity_ok, "reason": identity_reason},
    }


CHECKS = {"postgresql": check_postgres, "redis": check_redis, "email_delivery": check_email_delivery_configuration, "identity_provider": check_identity_provider_configuration}


def execute_required_checks():
    results=[]
    for service in ServiceDefinition.objects.filter(status="ACTIVE"):
        checker=CHECKS.get(service.code)
        if checker:
            ok, latency, reason=checker()
            results.append(HealthCheckResult.objects.create(service_code=service.code, check_code="canonical", state="HEALTHY" if ok else "UNHEALTHY", latency_ms=latency, observed_at=timezone.now(), failure_reason_safe=reason))
    return results
