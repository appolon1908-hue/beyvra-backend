"""Provider-neutral Polygon OMS contract proposal for Financial Service owners.

This module deliberately contains no HTTP transport. The Beyvra application must
never call OMS directly; it can only describe and validate the contract expected
at its existing Financial Service boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Callable, Mapping, Protocol


PROVIDER_ID = "polygon_oms"
PROVIDER_TYPE = "FINANCIAL_INFRASTRUCTURE"
ADAPTER_VERSION = "proposal-1"
SCHEMA_VERSION = "v0.11"


class CanonicalTransactionState(StrEnum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    REQUIRES_ACTION = "REQUIRES_ACTION"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"
    UNKNOWN = "UNKNOWN"


class CanonicalKycState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REQUIRES_UPDATE = "REQUIRES_UPDATE"


class CanonicalProviderError(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    COMPLIANCE_REQUIRED = "COMPLIANCE_REQUIRED"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class ProviderGovernanceState(StrEnum):
    DISCOVERED = "DISCOVERED"
    CONFIGURED = "CONFIGURED"
    CREDENTIAL_PRESENT = "CREDENTIAL_PRESENT"
    TECHNICALLY_CERTIFIED = "TECHNICALLY_CERTIFIED"
    SECURITY_APPROVED = "SECURITY_APPROVED"
    COMPLIANCE_APPROVED = "COMPLIANCE_APPROVED"
    FINANCIAL_APPROVED = "FINANCIAL_APPROVED"
    STAGING_APPROVED = "STAGING_APPROVED"
    PRODUCTION_APPROVED = "PRODUCTION_APPROVED"
    DISABLED = "DISABLED"


class OpenMoneyStackProvider(Protocol):
    """Financial Service-owned interface; implementations do not belong here."""

    def health(self) -> Mapping[str, object]: ...
    def capabilities(self) -> Mapping[str, object]: ...
    def create_customer(self, request: Mapping[str, object], idempotency_key: str) -> Mapping[str, object]: ...
    def get_customer(self, provider_ref: str) -> Mapping[str, object]: ...
    def update_customer(self, provider_ref: str, request: Mapping[str, object]) -> Mapping[str, object]: ...
    def create_wallet(self, customer_ref: str, request: Mapping[str, object], idempotency_key: str) -> Mapping[str, object]: ...
    def get_wallet(self, provider_ref: str) -> Mapping[str, object]: ...
    def list_wallets(self, customer_ref: str) -> Mapping[str, object]: ...
    def get_balance(self, wallet_ref: str) -> Mapping[str, object]: ...
    def create_quote(self, request: Mapping[str, object], idempotency_key: str) -> Mapping[str, object]: ...
    def get_quote(self, provider_ref: str) -> Mapping[str, object]: ...
    def execute_transaction(self, quote_ref: str, idempotency_key: str) -> Mapping[str, object]: ...
    def get_transaction(self, provider_ref: str) -> Mapping[str, object]: ...
    def list_transactions(self, customer_ref: str) -> Mapping[str, object]: ...
    def create_cash_in(self, request: Mapping[str, object], idempotency_key: str) -> Mapping[str, object]: ...


OMS_TRANSACTION_STATES = {
    "created": CanonicalTransactionState.CREATED,
    "pending": CanonicalTransactionState.PENDING,
    "processing": CanonicalTransactionState.PROCESSING,
    "awaitingAction": CanonicalTransactionState.REQUIRES_ACTION,
    "completed": CanonicalTransactionState.SETTLED,
    "failed": CanonicalTransactionState.FAILED,
    "cancelled": CanonicalTransactionState.CANCELLED,
    "reversed": CanonicalTransactionState.REVERSED,
}

OMS_KYC_STATES = {
    "notStarted": CanonicalKycState.NOT_STARTED,
    "pending": CanonicalKycState.PENDING,
    "inReview": CanonicalKycState.IN_REVIEW,
    "approved": CanonicalKycState.APPROVED,
    "rejected": CanonicalKycState.REJECTED,
    "expired": CanonicalKycState.EXPIRED,
    "requiresUpdate": CanonicalKycState.REQUIRES_UPDATE,
}

TERMINAL_STATES = {
    CanonicalTransactionState.SETTLED,
    CanonicalTransactionState.FAILED,
    CanonicalTransactionState.CANCELLED,
    CanonicalTransactionState.REVERSED,
}


def decimal_string(value: object) -> Decimal:
    """Parse an OMS amount without accepting binary floats or non-finite values."""
    if isinstance(value, (float, bool)) or value is None:
        raise ValueError("amount must be a decimal string or integer")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid decimal amount") from exc
    if not parsed.is_finite():
        raise ValueError("amount must be finite")
    return parsed


def canonical_transaction_state(provider_state: object) -> CanonicalTransactionState:
    return OMS_TRANSACTION_STATES.get(str(provider_state), CanonicalTransactionState.UNKNOWN)


def canonical_kyc_state(provider_state: object) -> CanonicalKycState:
    return OMS_KYC_STATES.get(str(provider_state), CanonicalKycState.IN_REVIEW)


def map_provider_error(status_code: int, body: object) -> CanonicalProviderError:
    code = body.get("code") if isinstance(body, Mapping) else None
    if code in {"compliance_required", "compliance_hold"}:
        return CanonicalProviderError.COMPLIANCE_REQUIRED
    if code == "insufficient_funds":
        return CanonicalProviderError.INSUFFICIENT_FUNDS
    if status_code == 409:
        return CanonicalProviderError.IDEMPOTENCY_CONFLICT
    if status_code in {400, 404, 422}:
        return CanonicalProviderError.VALIDATION_ERROR
    if status_code in {401, 403}:
        return CanonicalProviderError.OPERATION_NOT_ALLOWED
    if status_code in {408, 429, 500, 502, 503, 504}:
        return CanonicalProviderError.PROVIDER_UNAVAILABLE
    return CanonicalProviderError.UNKNOWN_OUTCOME


def validate_transaction_response(value: object) -> tuple[str, CanonicalTransactionState, Decimal]:
    if not isinstance(value, Mapping):
        raise ValueError("malformed provider response")
    try:
        provider_ref = str(value["id"])
        state = canonical_transaction_state(value["status"])
        amount = decimal_string(value["amount"])
    except KeyError as exc:
        raise ValueError("malformed provider response") from exc
    if not provider_ref:
        raise ValueError("malformed provider response")
    return provider_ref, state, amount


@dataclass(frozen=True)
class AssetNetwork:
    asset: str
    chain: str
    network_id: str
    decimals: int
    contract_address_if_applicable: str | None = None

    def __post_init__(self):
        if not self.asset or not self.chain or not self.network_id:
            raise ValueError("asset and network identity are required")
        if not 0 <= self.decimals <= 36:
            raise ValueError("unsupported precision")


@dataclass(frozen=True)
class EntityMapping:
    tenant_ref: str
    beyvra_account_ref: str
    oms_entity_ref: str
    provider_id: str = PROVIDER_ID
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "PENDING"


@dataclass(frozen=True)
class WalletMapping:
    tenant_ref: str
    wallet_ref: str
    provider_wallet_ref: str
    asset: str
    network: str
    custody_model: str
    status: str


def require_tenant_owner(request_tenant: str, resource_tenant: str) -> None:
    if not request_tenant or not hmac.compare_digest(request_tenant, resource_tenant):
        raise PermissionError("RESOURCE_NOT_FOUND")


@dataclass(frozen=True)
class Quote:
    quote_id: str
    operation_type: str
    input_asset: str
    input_amount: Decimal
    output_asset: str
    output_amount: Decimal
    fee: Decimal
    rate: Decimal
    expires_at: datetime
    provider_ref: str

    @classmethod
    def from_fixture(cls, value: Mapping[str, object]) -> "Quote":
        return cls(
            quote_id=str(value["quote_id"]),
            operation_type=str(value["operation_type"]),
            input_asset=str(value["input_asset"]),
            input_amount=decimal_string(value["input_amount"]),
            output_asset=str(value["output_asset"]),
            output_amount=decimal_string(value["output_amount"]),
            fee=decimal_string(value["fee"]),
            rate=decimal_string(value["rate"]),
            expires_at=datetime.fromisoformat(str(value["expires_at"]).replace("Z", "+00:00")),
            provider_ref=str(value["provider_ref"]),
        )


@dataclass(frozen=True)
class OutboundGate:
    polygon_oms_enabled: bool = False
    polygon_oms_production_enabled: bool = False
    polygon_oms_halted: bool = True
    all_financial_mutations_halted: bool = True
    environment_approved: bool = False
    credential_available: bool = False
    operation_approved: bool = False
    compliance_approved: bool = False
    financial_approved: bool = False
    feature_enabled: bool = False
    production_requested: bool = False

    def reason(self) -> str:
        checks = (
            (self.all_financial_mutations_halted, "GLOBAL_FINANCIAL_HALT"),
            (self.polygon_oms_halted, "POLYGON_OMS_HALTED"),
            (not self.polygon_oms_enabled, "POLYGON_OMS_DISABLED"),
            (self.production_requested and not self.polygon_oms_production_enabled, "PRODUCTION_NOT_APPROVED"),
            (not self.environment_approved, "ENVIRONMENT_NOT_APPROVED"),
            (not self.credential_available, "CREDENTIAL_UNAVAILABLE"),
            (not self.operation_approved, "OPERATION_NOT_APPROVED"),
            (not self.compliance_approved, "COMPLIANCE_REQUIRED"),
            (not self.financial_approved, "FINANCIAL_APPROVAL_REQUIRED"),
            (not self.feature_enabled, "FEATURE_DISABLED"),
        )
        for denied, reason in checks:
            if denied:
                return reason
        return "ALLOW"

    @property
    def allowed(self) -> bool:
        return self.reason() == "ALLOW"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0

    def record_failure(self) -> CircuitState:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
        return self.state

    def begin_probe(self) -> bool:
        if self.state is not CircuitState.OPEN:
            return False
        self.state = CircuitState.HALF_OPEN
        return True

    def record_success(self) -> CircuitState:
        self.failures = 0
        self.state = CircuitState.CLOSED
        return self.state


def verify_webhook_signature(
    raw_body: bytes,
    header: str | None,
    signing_key: bytes,
    *,
    now: int,
    tolerance_seconds: int = 300,
) -> bool:
    """Implement the documented `t=...,v1=...` OMS verification contract."""
    if not header or not signing_key:
        return False
    parts = {}
    for part in header.split(","):
        if "=" in part:
            key, value = part.split("=", 1)
            parts[key.strip()] = value.strip()
    timestamp, signature = parts.get("t"), parts.get("v1")
    if not timestamp or not signature:
        return False
    try:
        timestamp_number = int(timestamp)
        if abs(now - timestamp_number) > tolerance_seconds:
            return False
        received = bytes.fromhex(signature)
    except (ValueError, TypeError):
        return False
    expected = hmac.new(
        signing_key,
        timestamp.encode("ascii") + b"." + raw_body,
        hashlib.sha256,
    ).digest()
    return hmac.compare_digest(received, expected)


@dataclass
class FixtureInbox:
    """Deterministic stand-in for the proposed Financial Service inbox contract."""

    processed: set[str] = field(default_factory=set)
    last_sequence: dict[str, int] = field(default_factory=dict)
    states: dict[str, CanonicalTransactionState] = field(default_factory=dict)
    business_effects: int = 0
    dead_letters: list[str] = field(default_factory=list)

    def apply(self, raw_body: bytes) -> str:
        try:
            envelope = json.loads(raw_body)
            delivery_id = str(envelope["id"])
            event_type = envelope.get("event") or envelope.get("eventType")
            resource = envelope["data"]
            resource_id = str(resource["id"])
        except (json.JSONDecodeError, KeyError, TypeError):
            return "MALFORMED"
        if delivery_id in self.processed:
            return "DUPLICATE"
        if event_type != "transaction.statusChanged":
            self.dead_letters.append(delivery_id)
            self.processed.add(delivery_id)
            return "UNKNOWN_EVENT"
        sequence = envelope.get("sequence")
        if sequence is not None:
            sequence = int(sequence)
            last_sequence = self.last_sequence.get(resource_id)
            if last_sequence is not None and sequence <= last_sequence:
                self.processed.add(delivery_id)
                return "STALE"
            if sequence > 1 and (last_sequence is None or sequence > last_sequence + 1):
                self.dead_letters.append(delivery_id)
                self.processed.add(delivery_id)
                return "SEQUENCE_GAP"
        next_state = canonical_transaction_state(resource.get("status"))
        current_state = self.states.get(resource_id)
        if next_state is CanonicalTransactionState.UNKNOWN:
            self.dead_letters.append(delivery_id)
            self.processed.add(delivery_id)
            return "UNKNOWN_STATE"
        if current_state in TERMINAL_STATES and next_state != current_state:
            self.dead_letters.append(delivery_id)
            self.processed.add(delivery_id)
            return "INVALID_TRANSITION"
        self.processed.add(delivery_id)
        if sequence is not None:
            self.last_sequence[resource_id] = sequence
        self.states[resource_id] = next_state
        self.business_effects += 1
        return "APPLIED"


def resolve_unknown_outcome(
    operation_ref: str,
    lookup: Callable[[str], Mapping[str, object] | None],
    create: Callable[[], Mapping[str, object]],
) -> Mapping[str, object]:
    """Lookup before retry so a lost response cannot duplicate an operation."""
    existing = lookup(operation_ref)
    return existing if existing is not None else create()


def retry_delay(status_code: int, retry_after: str | None, attempt: int) -> float | None:
    if status_code not in {408, 429, 500, 502, 503, 504} or attempt >= 5:
        return None
    if status_code == 429 and retry_after:
        try:
            parsed = float(retry_after)
            return parsed if math.isfinite(parsed) and parsed >= 0 else None
        except ValueError:
            return None
    return float(min(2**attempt, 30))
