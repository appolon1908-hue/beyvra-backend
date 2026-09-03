from __future__ import annotations

import threading
import time
from pathlib import Path

import requests
from django.conf import settings

from apps.foundation.observability import record_live_effect


class EmailMiddlewareError(RuntimeError):
    def __init__(self, error_class: str, retryable: bool):
        self.error_class, self.retryable = error_class, retryable
        super().__init__(error_class)


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
        record_live_effect("transactional_email", "attempt")
        try:
            response = requests.post(
                settings.BEYVRA_EMAIL_API_URL + "/v1/email/messages",
                json=body,
                headers={"Authorization": "Bearer " + self.token()},
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
        record_live_effect("transactional_email", "success")
        return response.json()


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
