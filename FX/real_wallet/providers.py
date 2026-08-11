"""Provider-neutral boundaries; no provider is enabled by this module."""

from dataclasses import dataclass
from typing import Protocol


class ProviderUnavailable(RuntimeError):
    pass


class CustodyAdapter(Protocol):
    def create_address(self, *, connection_id: str, asset_network_id: str) -> dict: ...
    def create_transaction(self, *, connection_id: str, amount_atomic: str, destination: str) -> dict: ...
    def sign_transaction(self, *, provider_transaction_id: str) -> dict: ...
    def broadcast_transaction(self, *, signed_transaction: str) -> dict: ...
    def get_transaction(self, *, provider_transaction_id: str) -> dict: ...
    def get_balances(self, *, connection_id: str) -> list[dict]: ...
    def verify_webhook(self, *, body: bytes, headers: dict[str, str]) -> bool: ...


class ChainAdapter(Protocol):
    def validate_address(self, *, network_code: str, address: str) -> bool: ...
    def get_transaction(self, *, network_code: str, transaction_hash: str) -> dict: ...
    def get_confirmations(self, *, network_code: str, transaction_hash: str) -> int: ...
    def get_latest_block(self, *, network_code: str) -> dict: ...
    def estimate_network_fee(self, *, network_code: str, transaction: dict) -> str: ...
    def detect_reorganization(self, *, network_code: str, transaction_hash: str) -> bool: ...


@dataclass(frozen=True)
class DisabledCustodyAdapter:
    reason: str = "custody provider is not configured"

    def _disabled(self, **kwargs):
        raise ProviderUnavailable(self.reason)

    create_address = _disabled
    create_transaction = _disabled
    sign_transaction = _disabled
    broadcast_transaction = _disabled
    get_transaction = _disabled
    get_balances = _disabled
    verify_webhook = _disabled


@dataclass(frozen=True)
class DisabledChainAdapter:
    reason: str = "blockchain provider is not configured"

    def _disabled(self, **kwargs):
        raise ProviderUnavailable(self.reason)

    validate_address = _disabled
    get_transaction = _disabled
    get_confirmations = _disabled
    get_latest_block = _disabled
    estimate_network_fee = _disabled
    detect_reorganization = _disabled


@dataclass
class SandboxCustodyAdapter:
    """Deterministic test adapter; never valid for production settings."""
    environment: str = "sandbox"

    def _check(self):
        if self.environment != "sandbox":
            raise ProviderUnavailable("sandbox adapter cannot run outside sandbox")

    def create_address(self, *, connection_id, asset_network_id):
        self._check()
        return {"provider_address_id": f"sandbox-address:{connection_id}:{asset_network_id}"}

    def create_transaction(self, *, connection_id, amount_atomic, destination):
        self._check()
        return {"provider_transaction_id": f"sandbox-tx:{connection_id}:{destination}:{amount_atomic}"}

    def sign_transaction(self, *, provider_transaction_id):
        self._check()
        return {"signed_transaction": f"sandbox-signed:{provider_transaction_id}"}

    def broadcast_transaction(self, *, signed_transaction):
        self._check()
        return {"transaction_hash": f"sandbox-broadcast:{signed_transaction}"}

    def get_transaction(self, *, provider_transaction_id):
        self._check()
        return {"provider_transaction_id": provider_transaction_id, "status": "PENDING"}

    def get_balances(self, *, connection_id):
        self._check()
        return []

    def verify_webhook(self, *, body, headers):
        self._check()
        return False


@dataclass
class SandboxChainAdapter:
    environment: str = "sandbox"

    def _check(self):
        if self.environment != "sandbox":
            raise ProviderUnavailable("sandbox adapter cannot run outside sandbox")

    def validate_address(self, *, network_code, address):
        self._check()
        return bool(address.startswith("sandbox_"))

    def get_transaction(self, *, network_code, transaction_hash):
        self._check()
        return {"transaction_hash": transaction_hash, "confirmations": 0}

    def get_confirmations(self, *, network_code, transaction_hash):
        self._check()
        return 0

    def get_latest_block(self, *, network_code):
        self._check()
        return {"height": 0, "hash": "sandbox-genesis"}

    def estimate_network_fee(self, *, network_code, transaction):
        self._check()
        return "0"

    def detect_reorganization(self, *, network_code, transaction_hash):
        self._check()
        return False
