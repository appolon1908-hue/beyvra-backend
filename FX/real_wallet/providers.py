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
