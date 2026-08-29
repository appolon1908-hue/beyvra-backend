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


def _evidence_passed(name):
    return str(getattr(settings, name, "") or "").strip().lower() in {"1", "true", "yes", "pass", "passed", "enabled"}


def _evidence_blocked(name):
    return str(getattr(settings, name, "") or "").strip().lower() in {"blocked", "pass", "passed", "true", "1", "yes"}


def _beyvra_mail_domain_evidence_required():
    names = (
        "BEYVRA_FROM_DOMAIN",
        "KLYROW_SMTP_CONNECTIVITY",
        "STARTTLS",
        "SPF",
        "DKIM",
        "DMARC",
        "DIRECT_APP_SMTP_ACCESS",
        "DIRECT_APP_KLYROW_ACCESS",
        "PLAINTEXT_SMTP_SECRET_IN_GIT",
    )
    return settings.READINESS_ENFORCE_IDENTITY_EMAIL or any(str(getattr(settings, name, "") or "").strip() for name in names)


def check_beyvra_mail_domain_activation():
    start = time.perf_counter()
    try:
        if not _beyvra_mail_domain_evidence_required():
            return True, (time.perf_counter() - start) * 1000, "NOT_ENFORCED"
        if str(getattr(settings, "BEYVRA_FROM_DOMAIN", "") or "").strip().lower() != "beyvra.com":
            return False, (time.perf_counter() - start) * 1000, "BEYVRA_FROM_DOMAIN_NOT_VERIFIED"
        for name in ("KLYROW_SMTP_CONNECTIVITY", "STARTTLS", "SPF", "DKIM", "DMARC"):
            if not _evidence_passed(name):
                return False, (time.perf_counter() - start) * 1000, f"{name}_NOT_VERIFIED"
        for name in ("DIRECT_APP_SMTP_ACCESS", "DIRECT_APP_KLYROW_ACCESS", "PLAINTEXT_SMTP_SECRET_IN_GIT"):
            if not _evidence_blocked(name):
                return False, (time.perf_counter() - start) * 1000, f"{name}_NOT_BLOCKED"
        return True, (time.perf_counter() - start) * 1000, ""
    except Exception:
        return False, (time.perf_counter() - start) * 1000, "MAIL_DOMAIN_EVIDENCE_INVALID"


def check_email_delivery_configuration():
    start = time.perf_counter()
    try:
        if settings.KEYCLOAK_IDENTITY_ENABLED and settings.KEYCLOAK_REGISTRATION_ENABLED and settings.KEYCLOAK_RESET_PASSWORD_ENABLED and settings.KEYCLOAK_EMAIL_VERIFICATION and not (settings.TRANSACTIONAL_EMAIL_ENABLED or getattr(settings, "WELCOME_EMAIL_ENABLED", False)):
            return True, (time.perf_counter() - start) * 1000, "KEYCLOAK_AUTHORITY"
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
        if not (settings.KEYCLOAK_REGISTRATION_ENABLED and settings.KEYCLOAK_RESET_PASSWORD_ENABLED and settings.KEYCLOAK_EMAIL_VERIFICATION):
            return False, (time.perf_counter() - start) * 1000, "KEYCLOAK_EMAIL_CAPABILITY_MISSING"
        if settings.READINESS_ENFORCE_IDENTITY_EMAIL and not _evidence_blocked("RESET_TOKEN_OUTSIDE_KEYCLOAK"):
            return False, (time.perf_counter() - start) * 1000, "RESET_TOKEN_OUTSIDE_KEYCLOAK_NOT_BLOCKED"
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
            "beyvra_mail_domain": {"ok": True, "reason": "NOT_ENFORCED"},
        }
    email_ok, _, email_reason = check_email_delivery_configuration()
    identity_ok, _, identity_reason = check_identity_provider_configuration()
    domain_ok, _, domain_reason = check_beyvra_mail_domain_activation()
    return {
        "email_delivery": {"ok": email_ok, "reason": email_reason},
        "identity_provider": {"ok": identity_ok, "reason": identity_reason},
        "beyvra_mail_domain": {"ok": domain_ok, "reason": domain_reason},
    }


CHECKS = {"postgresql": check_postgres, "redis": check_redis, "email_delivery": check_email_delivery_configuration, "identity_provider": check_identity_provider_configuration, "beyvra_mail_domain": check_beyvra_mail_domain_activation}


def execute_required_checks():
    results=[]
    for service in ServiceDefinition.objects.filter(status="ACTIVE"):
        checker=CHECKS.get(service.code)
        if checker:
            ok, latency, reason=checker()
            results.append(HealthCheckResult.objects.create(service_code=service.code, check_code="canonical", state="HEALTHY" if ok else "UNHEALTHY", latency_ms=latency, observed_at=timezone.now(), failure_reason_safe=reason))
    return results
