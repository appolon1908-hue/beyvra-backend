import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urljoin

import requests
from django.conf import settings


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

    @property
    def state(self):
        if self.opened_at is None:
            return CircuitState.CLOSED
        if self.clock() - self.opened_at >= self.recovery_seconds:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    def before_request(self):
        if self.state == CircuitState.OPEN:
            raise CircuitOpen("SERVICE_TEMPORARILY_UNAVAILABLE")

    def success(self):
        self.failures, self.opened_at = 0, None

    def failure(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = self.clock()


class FinancialServiceClient:
    SAFE_RETRY_METHODS = {"GET", "HEAD"}
    TRANSIENT_STATUS = {500, 502, 503, 504}

    def __init__(self, session=None, breaker=None):
        self.base_url = settings.FINANCIAL_SERVICE_URL.rstrip("/") + "/"
        self.api_version = settings.FINANCIAL_SERVICE_API_VERSION
        self.cert = (settings.FINANCIAL_SERVICE_CLIENT_CERT, settings.FINANCIAL_SERVICE_CLIENT_KEY)
        self.ca = settings.FINANCIAL_SERVICE_CA_CERT
        self.timeout = (settings.FINANCIAL_SERVICE_CONNECT_TIMEOUT_SECONDS, settings.FINANCIAL_SERVICE_REQUEST_TIMEOUT_SECONDS)
        self.retry_count = settings.FINANCIAL_SERVICE_RETRY_COUNT
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

    def _request(self, method, path, context, *, payload=None, idempotency_key=None):
        method = method.upper()
        attempts = 1 + (self.retry_count if method in self.SAFE_RETRY_METHODS else 0)
        url = urljoin(self.base_url, f"internal/{self.api_version}/{path.lstrip('/')}")
        for attempt in range(attempts):
            self.breaker.before_request()
            try:
                response = self.session.request(
                    method, url, json=payload, headers=self._headers(context, idempotency_key),
                    cert=self.cert, verify=self.ca, timeout=self.timeout,
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
            if response.status_code in self.TRANSIENT_STATUS:
                self.breaker.failure()
                if method in self.SAFE_RETRY_METHODS and attempt + 1 < attempts:
                    continue
            else:
                self.breaker.success()
            if response.status_code >= 400:
                code = body.get("code", "FINANCIAL_SERVICE_ERROR")
                error_class = FinancialFeatureDisabled if code == "FEATURE_DISABLED" else FinancialServiceError
                raise error_class(code, status=response.status_code)
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
