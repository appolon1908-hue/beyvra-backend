"""Provider-ready market-data contracts; no provider is activated by default."""
from dataclasses import dataclass
from typing import Protocol, Sequence

from .market_events import MarketEvent


@dataclass(frozen=True)
class ProviderMetadata:
    provider_code: str
    provider_version: str
    license_reference: str | None
    delay_status: str
    quality_status: str
    supported_symbols: frozenset[str]
    supported_timeframes: frozenset[str]


class MarketDataProvider(Protocol):
    metadata: ProviderMetadata
    def historical_candles(self, *, symbol: str, timeframe: str, limit: int) -> Sequence[dict]: ...
    def health(self) -> dict: ...


class DisabledMarketDataProvider:
    metadata = ProviderMetadata("disabled", "0", None, "UNKNOWN", "UNAVAILABLE", frozenset(), frozenset())
    def historical_candles(self, **kwargs):
        raise RuntimeError("no approved market provider is configured")
    def health(self):
        return {"status": "DISCONNECTED", "provider": self.metadata.provider_code}


def validate_provider_event(metadata: ProviderMetadata, event: MarketEvent) -> bool:
    return event.channel.split(".")[1].upper() in metadata.supported_symbols and event.schema_version == "1"
