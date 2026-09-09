from __future__ import annotations

import ipaddress
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from django.conf import settings

from apps.foundation.observability import record_live_effect


class EmailMiddlewareError(RuntimeError):
    def __init__(self, error_class: str, retryable: bool):
        self.error_class, self.retryable = error_class, retryable
        super().__init__(error_class)


def _canonical_email_origin(value: str) -> str:
    """Normalize an exact origin without permitting URL parser ambiguities."""
    if not isinstance(value, str) or not value or any(
        ord(char) <= 32 or ord(char) >= 127 for char in value
    ):
        raise ValueError("Invalid email origin")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().removesuffix(".")
    port = parsed.port  # Validate malformed and out-of-range ports now.
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or "?" in value
        or "#" in value
    ):
        raise ValueError("Invalid email origin")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.split(".")
        ):
            raise ValueError("Invalid email hostname") from None
        authority = host
    else:
        authority = f"[{address.compressed}]" if address.version == 6 else str(address)
    if port is not None and port != (443 if parsed.scheme == "https" else 80):
        authority += f":{port}"
    return f"{parsed.scheme}://{authority}"


class EmailMiddlewareClient:
    _lock = threading.Lock()
    _token = ""
    _expires_at = 0.0

    def _credential(self) -> str:
        path = Path(settings.BEYVRA_EMAIL_CLIENT_SECRET_FILE)
        value = path.read_text(encoding="utf-8").strip()
        if not value:
            raise EmailMiddlewareError("AUTHENTICATION_FAILURE", False)
        return value

    def _middleware_base_url(self) -> str:
        # Destination and trust policy are independent configuration values.
        # Never derive the allowlist from the destination being validated.
        configured_env = os.environ.get("BEYVRA_EMAIL_API_URL")
        configured_value = (
            configured_env
            if configured_env is not None
            else getattr(settings, "BEYVRA_EMAIL_API_URL", "")
        )
        value = str(configured_value or "").strip()
        if not value:
            raise EmailMiddlewareError("MIDDLEWARE_ENDPOINT_NOT_CONFIGURED", True)
        try:
            origin = _canonical_email_origin(value)
        except ValueError as exc:
            raise EmailMiddlewareError("MIDDLEWARE_ENDPOINT_INVALID", False) from exc
        host = urlsplit(origin).hostname
        forbidden_hosts = {
            "api.codestra.co",
            "api.codestra.agency",
            "api.klyrow.com",
            "mail.klyrow.com",
        }
        if host in forbidden_hosts:
            if configured_env is None and host == "api.codestra.co":
                # Preserve durable intent when only the legacy fallback exists.
                raise EmailMiddlewareError("MIDDLEWARE_ENDPOINT_NOT_CONFIGURED", True)
            raise EmailMiddlewareError("DIRECT_INTEGRATION_BYPASS_BLOCKED", False)

        allowed = os.environ.get("BEYVRA_EMAIL_ALLOWED_ORIGINS")
        if allowed is None:
            allowed = getattr(settings, "BEYVRA_EMAIL_ALLOWED_ORIGINS", ())
        if isinstance(allowed, str):
            allowed = [entry.strip() for entry in allowed.split(",")]
            if allowed == [""]:
                allowed = []
        if not isinstance(allowed, (list, tuple, set, frozenset)):
            raise EmailMiddlewareError("MIDDLEWARE_ALLOWLIST_INVALID", False)
        if not allowed:
            raise EmailMiddlewareError("MIDDLEWARE_ALLOWLIST_NOT_CONFIGURED", True)
        try:
            allowed_origins = {_canonical_email_origin(entry) for entry in allowed}
        except ValueError as exc:
            raise EmailMiddlewareError("MIDDLEWARE_ALLOWLIST_INVALID", False) from exc
        if origin not in allowed_origins:
            raise EmailMiddlewareError("DIRECT_INTEGRATION_BYPASS_BLOCKED", False)
        return origin

    def token(self) -> str:
        cls = type(self)
        with cls._lock:
            if cls._token and cls._expires_at > time.monotonic() + 30:
                return cls._token
            try:
                response = requests.post(
                    settings.BEYVRA_EMAIL_TOKEN_URL,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": "beyvra-email-production",
                        "client_secret": self._credential(),
                        "scope": "email.send email.read",
                    },
                    timeout=5,
                    allow_redirects=False,
                )
                response.raise_for_status()
                value = response.json()
                cls._token = str(value["access_token"])
                cls._expires_at = time.monotonic() + min(
                    int(value.get("expires_in", 300)),
                    300,
                )
                return cls._token
            except (
                OSError,
                requests.RequestException,
                KeyError,
                ValueError,
            ) as exc:
                raise EmailMiddlewareError(
                    "AUTHENTICATION_FAILURE",
                    isinstance(exc, requests.RequestException),
                ) from exc

    def submit(self, item, parameters: dict) -> dict:
        if getattr(settings, "KEYCLOAK_IDENTITY_ENABLED", False) and item.template_key in {
            "password_reset",
            "account_verification",
            "email_otp",
        }:
            raise EmailMiddlewareError("IDENTITY_MAIL_MUST_USE_KEYCLOAK", False)

        category = category_for(item.template_key)
        body = {
            "notification_id": str(item.notification_id),
            "event_id": item.event_id,
            "correlation_id": str(item.correlation_id),
            "idempotency_key": item.idempotency_key,
            "user_id": item.user_id_ref,
            "account_id": item.account_id_ref,
            "template_id": normalize_template(item.template_key),
            "template_version": int(item.template_version),
            "recipient": item.recipient_email,
            "event_type": item.event_type,
            "category": category,
            "locale": item.locale,
            "parameters": parameters,
        }

        endpoint = self._middleware_base_url() + "/v1/email/messages"
        token = self.token()
        record_live_effect("transactional_email", "attempt")
        try:
            response = requests.post(
                endpoint,
                json=body,
                headers={"Authorization": "Bearer " + token},
                timeout=10,
                allow_redirects=False,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            record_live_effect("transactional_email", "failure")
            raise EmailMiddlewareError("NETWORK_FAILURE", True) from exc

        if response.status_code == 429:
            record_live_effect("transactional_email", "failure")
            raise EmailMiddlewareError("RATE_LIMITED", True)
        if response.status_code >= 500:
            record_live_effect("transactional_email", "failure")
            raise EmailMiddlewareError("TEMPORARY_PROVIDER_FAILURE", True)
        if response.status_code >= 400:
            record_live_effect("transactional_email", "failure")
            raise EmailMiddlewareError("POLICY_REJECTION", False)
        if not 200 <= response.status_code < 300:
            record_live_effect("transactional_email", "failure")
            raise EmailMiddlewareError("INVALID_RESPONSE", False)

        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Expected an object response")
        except ValueError as exc:
            record_live_effect("transactional_email", "failure")
            raise EmailMiddlewareError("INVALID_RESPONSE", False) from exc

        record_live_effect("transactional_email", "success")
        return result


def normalize_template(value: str) -> str:
    return {
        "email_otp": "account_verification",
        "welcome_email": "welcome",
    }.get(value, value)


def category_for(template_id: str) -> str:
    if template_id in {
        "account_verification",
        "email_otp",
        "welcome",
        "welcome_email",
        "password_reset",
        "password_changed",
        "email_changed",
        "account_locked",
        "account_unlocked",
    }:
        return "ACCOUNT"
    if template_id in {
        "new_login",
        "suspicious_login",
        "new_device",
        "two_factor_changed",
        "security_settings_changed",
        "api_key_created",
        "api_key_revoked",
    }:
        return "SECURITY"
    if template_id.startswith(("order_", "position_", "margin_", "risk_")):
        return "TRADING"
    if template_id.startswith(("deposit_", "withdrawal_")):
        return "FUNDS"
    if "statement" in template_id:
        return "STATEMENTS"
    if template_id.startswith("support_"):
        return "SUPPORT"
    return "SYSTEM"
