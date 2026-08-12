import time
import threading
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urljoin

import requests
from django.conf import settings

from .metrics import (
    CIRCUIT_STATE, DURATION, FAILURES, IDEMPOTENCY_CONFLICTS, REQUESTS,
    UNKNOWN_OUTCOMES, failure_category,
)


class FinancialServiceError(RuntimeError):
    def __init__(self, code, detail="Financial service request failed.", status=503):
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, status


class FinancialFeatureDisabled(FinancialServiceError):
    pass


class UnknownFinancialOutcome(FinancialServiceError):
    """A mutation may have committed; callers must look it up before retrying."""


class CircuitOpen(FinancialServiceError):
    pass


class FinancialContractUnavailable(FinancialServiceError):
    pass


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class FinancialContext:
    tenant_ref: uuid.UUID
    subject_ref: uuid.UUID
    request_id: str
    correlation_id: uuid.UUID


class CircuitBreaker:
    def __init__(self, threshold=5, recovery_seconds=30, clock=time.monotonic):
        self.threshold = threshold
        self.recovery_seconds = recovery_seconds
        self.clock = clock
        self.failures = 0
        self.opened_at = None
        self._half_open_probe = False
        self._lock = threading.Lock()

    def _state_unlocked(self):
        if self.opened_at is None:
            return CircuitState.CLOSED
        if self.clock() - self.opened_at >= self.recovery_seconds:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    @property
    def state(self):
        with self._lock:
            return self._state_unlocked()

    def before_request(self):
        with self._lock:
            state = self._state_unlocked()
            CIRCUIT_STATE.set({CircuitState.CLOSED: 0, CircuitState.HALF_OPEN: 1, CircuitState.OPEN: 2}[state])
            if state == CircuitState.OPEN or (state == CircuitState.HALF_OPEN and self._half_open_probe):
                raise CircuitOpen("SERVICE_TEMPORARILY_UNAVAILABLE")
            if state == CircuitState.HALF_OPEN:
                self._half_open_probe = True

    def success(self):
        with self._lock:
            self.failures, self.opened_at, self._half_open_probe = 0, None, False
            CIRCUIT_STATE.set(0)

    def failure(self):
        with self._lock:
            was_half_open = self._state_unlocked() == CircuitState.HALF_OPEN
            self.failures += 1
            if was_half_open or self.failures >= self.threshold:
                self.opened_at = self.clock()
            self._half_open_probe = False
            CIRCUIT_STATE.set(2 if self.opened_at is not None else 0)


class FinancialServiceClient:
    SAFE_RETRY_METHODS = {"GET", "HEAD"}
    TRANSIENT_STATUS = {500, 502, 503, 504}

    def __init__(self, session=None, breaker=None, clock=None):
        self.base_url = settings.FINANCIAL_SERVICE_URL.rstrip("/") + "/"
        self.api_version = settings.FINANCIAL_SERVICE_API_VERSION
        self.cert = (settings.FINANCIAL_SERVICE_CLIENT_CERT, settings.FINANCIAL_SERVICE_CLIENT_KEY)
        self.ca = settings.FINANCIAL_SERVICE_CA_CERT
        self.timeout = (settings.FINANCIAL_SERVICE_CONNECT_TIMEOUT_SECONDS, settings.FINANCIAL_SERVICE_REQUEST_TIMEOUT_SECONDS)
        self.retry_count = settings.FINANCIAL_SERVICE_RETRY_COUNT
        self.overall_deadline = settings.FINANCIAL_SERVICE_OVERALL_DEADLINE_SECONDS
        if self.overall_deadline <= 0:
            raise ValueError("Financial Service overall deadline must be positive")
        self.clock = clock or time.monotonic
        self.session = session or requests.Session()
        self.breaker = breaker or CircuitBreaker(
            settings.FINANCIAL_SERVICE_CIRCUIT_FAILURE_THRESHOLD,
            settings.FINANCIAL_SERVICE_CIRCUIT_RECOVERY_SECONDS,
        )
        if not self.base_url.startswith("https://"):
            raise ValueError("Financial Service requires HTTPS")
        for path in (*self.cert, self.ca):
            resolved = Path(path)
            if not resolved.is_file() or resolved.is_symlink():
                raise RuntimeError("Financial Service TLS material is unavailable")

    def _headers(self, context, idempotency_key):
        headers = {
            "X-Tenant-Ref": str(context.tenant_ref),
            "X-Subject-Ref": str(context.subject_ref),
            "X-Request-ID": context.request_id,
            "X-Correlation-ID": str(context.correlation_id),
            "X-Caller-Service": settings.FINANCIAL_SERVICE_CALLER,
            "X-Service-Scopes": settings.FINANCIAL_SERVICE_SCOPES,
            "X-Service-Audience": settings.FINANCIAL_SERVICE_AUDIENCE,
            "Accept": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    @staticmethod
    def _safe_code(code):
        mapping = {
            "VALIDATION_FAILED": "VALIDATION_ERROR",
            "RESOURCE_NOT_FOUND": "NOT_FOUND",
            "AUTHENTICATION_REQUIRED": "RESTRICTION",
            "AUTHORIZATION_DENIED": "RESTRICTION",
            "TENANT_MISMATCH": "RESTRICTION",
        }
        return mapping.get(code, code if code in {
            "FEATURE_DISABLED", "INSUFFICIENT_AVAILABLE_BALANCE",
            "IDEMPOTENCY_CONFLICT", "WITHDRAWAL_NOT_CANCELLABLE",
            "WITHDRAWAL_ALREADY_PROCESSED",
        } else "FINANCIAL_SERVICE_ERROR")

    @staticmethod
    def _validate_mutation(idempotency_key, payload):
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 255:
            raise FinancialServiceError("VALIDATION_ERROR", status=400)
        if not all(character.isalnum() or character in "._:-" for character in idempotency_key):
            raise FinancialServiceError("VALIDATION_ERROR", status=400)
        if not isinstance(payload, dict):
            raise FinancialServiceError("VALIDATION_ERROR", status=400)

    def _attempt_timeout(self, deadline):
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise FinancialServiceError("TRANSIENT_UNAVAILABLE")
        connect = min(self.timeout[0], max(0.001, remaining / 2))
        request = min(self.timeout[1], max(0.001, remaining - connect))
        return connect, request

    def _request(self, method, path, context, *, payload=None, idempotency_key=None):
        method = method.upper()
        if method not in self.SAFE_RETRY_METHODS:
            self._validate_mutation(idempotency_key, payload)
        started = self.clock()
        deadline = started + self.overall_deadline
        outcome = "success"
        try:
            return self._request_attempts(
                method, path, context, payload=payload,
                idempotency_key=idempotency_key, deadline=deadline,
            )
        except FinancialFeatureDisabled:
            outcome = "feature_disabled"
            raise
        except UnknownFinancialOutcome as exc:
            outcome = "unknown_outcome"
            UNKNOWN_OUTCOMES.inc()
            FAILURES.labels(category="UNKNOWN_OUTCOME").inc()
            raise exc
        except FinancialServiceError as exc:
            outcome = "failure"
            if exc.code == "IDEMPOTENCY_CONFLICT":
                IDEMPOTENCY_CONFLICTS.inc()
            FAILURES.labels(category=failure_category(exc.code)).inc()
            raise
        finally:
            REQUESTS.labels(method=method, outcome=outcome).inc()
            DURATION.labels(method=method).observe(max(0, self.clock() - started))

    def _request_attempts(self, method, path, context, *, payload, idempotency_key, deadline):
        attempts = 1 + (self.retry_count if method in self.SAFE_RETRY_METHODS else 0)
        url = urljoin(self.base_url, f"internal/{self.api_version}/{path.lstrip('/')}")
        for attempt in range(attempts):
            attempt_timeout = self._attempt_timeout(deadline)
            self.breaker.before_request()
            try:
                response = self.session.request(
                    method, url, json=payload, headers=self._headers(context, idempotency_key),
                    cert=self.cert, verify=self.ca, timeout=attempt_timeout,
                )
            except requests.exceptions.SSLError as exc:
                self.breaker.failure()
                raise FinancialServiceError("MTLS_AUTHENTICATION_FAILED") from exc
            except (requests.Timeout, requests.ConnectionError) as exc:
                self.breaker.failure()
                if method not in self.SAFE_RETRY_METHODS:
                    raise UnknownFinancialOutcome("UNKNOWN_OUTCOME") from exc
                if attempt + 1 == attempts:
                    raise FinancialServiceError("TRANSIENT_UNAVAILABLE") from exc
                continue
            try:
                body = response.json()
            except ValueError:
                body = {}
            raw_code = body.get("code", "FINANCIAL_SERVICE_ERROR")
            code = self._safe_code(raw_code)
            if response.status_code >= 400 and code == "FEATURE_DISABLED":
                self.breaker.success()
                raise FinancialFeatureDisabled(code, status=response.status_code)
            if response.status_code in self.TRANSIENT_STATUS:
                self.breaker.failure()
                if method in self.SAFE_RETRY_METHODS and attempt + 1 < attempts and self.clock() < deadline:
                    continue
            else:
                self.breaker.success()
            if response.status_code >= 400:
                raise FinancialServiceError(code, status=response.status_code)
            return body
        raise FinancialServiceError("TRANSIENT_UNAVAILABLE")

    def health(self, context): return self._request("GET", "health/live", context)
    def readiness(self, context): return self._request("GET", "health/ready", context)
    def list_wallets(self, context): return self._request("GET", "wallets", context)
    def get_wallet(self, context, wallet_id): return self._request("GET", f"wallets/{uuid.UUID(str(wallet_id))}", context)
    def get_balances(self, context, wallet_id): return self._request("GET", f"wallets/{uuid.UUID(str(wallet_id))}/balances", context)
    def list_deposits(self, context): return self._request("GET", "deposits", context)
    def list_withdrawals(self, context): return self._request("GET", "withdrawals", context)
    def reserve_funds(self, context, payload, key): raise FinancialContractUnavailable("CONTRACT_UNAVAILABLE", "reservation is absent from authoritative v1")
    def release_reservation(self, context, reservation_id, payload, key): raise FinancialContractUnavailable("CONTRACT_UNAVAILABLE", "release is absent from authoritative v1")
    def settle_trade(self, context, payload, key): raise FinancialContractUnavailable("CONTRACT_UNAVAILABLE", "settlement is absent from authoritative v1")
    def create_deposit_intent(self, context, payload, key): raise FinancialContractUnavailable("CONTRACT_UNAVAILABLE", "deposit intent is absent from authoritative v1")
    def request_withdrawal(self, context, payload, key): return self._request("POST", "withdrawals", context, payload=payload, idempotency_key=key)
    def request_transfer(self, context, payload, key): return self._request("POST", "transfers", context, payload=payload, idempotency_key=key)
    def lookup_operation(self, context, reference): raise FinancialContractUnavailable("CONTRACT_UNAVAILABLE", "operation lookup is absent from authoritative v1")
    def resolve_unknown_outcome(self, context, reference):
        """Lookup only. This method intentionally never retries a mutation."""
        return self.lookup_operation(context, reference)
