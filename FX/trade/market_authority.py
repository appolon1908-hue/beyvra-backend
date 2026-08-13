"""Canonical, provider-neutral market authority primitives.

This module performs no network I/O and activates no provider.  Adapters must
pass governance before feeding these contracts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import math
import random
import time
import uuid
from typing import Callable, Iterable, Protocol

UTC = timezone.utc
NORMALIZER_VERSION = "1.0.0"


class AuthorityError(ValueError): pass
class UnknownInstrument(AuthorityError): pass
class AmbiguousSymbol(AuthorityError): pass
class MalformedMarketData(AuthorityError): pass
class StaleMarketData(AuthorityError): pass
class RateLimited(AuthorityError): pass


class MarketState(str, Enum):
    PREOPEN="PREOPEN"; OPEN="OPEN"; HALTED="HALTED"; CLOSED="CLOSED"; POSTMARKET="POSTMARKET"; UNKNOWN="UNKNOWN"


class FreshnessState(str, Enum):
    FRESH="FRESH"; DEGRADED="DEGRADED"; STALE="STALE"; UNAVAILABLE="UNAVAILABLE"


class ConnectionState(str, Enum):
    DISCONNECTED="DISCONNECTED"; CONNECTING="CONNECTING"; AUTHENTICATING="AUTHENTICATING"; SUBSCRIBING="SUBSCRIBING"; LIVE="LIVE"; DEGRADED="DEGRADED"; BACKOFF="BACKOFF"; DISABLED="DISABLED"


class FailoverState(str, Enum):
    PRIMARY_LIVE="PRIMARY_LIVE"; PRIMARY_DEGRADED="PRIMARY_DEGRADED"; FAILOVER_PENDING="FAILOVER_PENDING"; SECONDARY_LIVE="SECONDARY_LIVE"; NO_AUTHORITY="NO_AUTHORITY"


def _utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MalformedMarketData(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _positive(value, field_name: str, *, zero=False) -> Decimal:
    try: result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc: raise MalformedMarketData(f"invalid {field_name}") from exc
    if not result.is_finite() or result < 0 or (not zero and result == 0):
        raise MalformedMarketData(f"invalid {field_name}")
    return result


@dataclass(frozen=True)
class Provenance:
    provider_id: str
    provider_message_type: str
    provider_timestamp: datetime
    received_at: datetime
    source_type: str
    normalizer_version: str = NORMALIZER_VERSION
    raw_message_hash: str | None = None
    def __post_init__(self):
        object.__setattr__(self, "provider_timestamp", _utc(self.provider_timestamp, "provider_timestamp"))
        object.__setattr__(self, "received_at", _utc(self.received_at, "received_at"))
        if self.source_type not in {"REST", "WEBSOCKET", "SERVER_AGGREGATE", "CERTIFIED_INTERNAL"}: raise MalformedMarketData("invalid source_type")


@dataclass(frozen=True)
class Instrument:
    instrument_id: str; symbol: str; display_symbol: str; asset_class: str
    base_asset: str | None; quote_asset: str | None; venue: str
    provider_symbol_map: dict[str, str]; status: str; price_precision: int
    quantity_precision: int; timezone: str


class InstrumentRegistry:
    def __init__(self, instruments: Iterable[Instrument]):
        instruments = tuple(instruments)
        self._items = {i.instrument_id: i for i in instruments}
        if len(self._items) != len(instruments): raise AmbiguousSymbol("duplicate instrument_id")
        reverse: dict[tuple[str, str], str] = {}
        for item in self._items.values():
            for provider, symbol in item.provider_symbol_map.items():
                key=(provider, symbol)
                if key in reverse: raise AmbiguousSymbol(f"duplicate mapping {provider}:{symbol}")
                reverse[key]=item.instrument_id
        self._reverse=reverse
    def get(self, instrument_id: str) -> Instrument:
        try: return self._items[instrument_id]
        except KeyError as exc: raise UnknownInstrument(instrument_id) from exc
    def resolve(self, provider_id: str, provider_symbol: str, *, asset_class=None, venue=None) -> Instrument:
        try: item=self.get(self._reverse[(provider_id, provider_symbol)])
        except KeyError as exc: raise UnknownInstrument(f"{provider_id}:{provider_symbol}") from exc
        if asset_class and item.asset_class != asset_class: raise AmbiguousSymbol("asset-class mismatch")
        if venue and item.venue != venue: raise AmbiguousSymbol("venue mismatch")
        return item
    def all(self): return tuple(sorted(self._items.values(), key=lambda item: item.instrument_id))


@dataclass(frozen=True)
class Quote:
    instrument_id: str; bid: Decimal | None; ask: Decimal | None
    bid_size: Decimal | None; ask_size: Decimal | None; last: Decimal | None
    provider_timestamp: datetime; received_at: datetime; provider_id: str
    sequence: str | None; delayed: bool; stale: bool; provenance: Provenance
    suspect: bool = False
    def __post_init__(self):
        object.__setattr__(self,"provider_timestamp",_utc(self.provider_timestamp,"provider_timestamp"))
        object.__setattr__(self,"received_at",_utc(self.received_at,"received_at"))
        if self.provider_timestamp != self.provenance.provider_timestamp or self.received_at != self.provenance.received_at:
            raise MalformedMarketData("quote timestamps must match provenance")
        for name in ("bid","ask","bid_size","ask_size","last"):
            value=getattr(self,name)
            if value is not None: object.__setattr__(self,name,_positive(value,name,zero=name.endswith("size")))
        if self.bid is not None and self.ask is not None and self.bid > self.ask: object.__setattr__(self,"suspect",True)


@dataclass(frozen=True)
class TradeTick:
    instrument_id: str; price: Decimal; size: Decimal; trade_id: str | None
    provider_timestamp: datetime; received_at: datetime; provider_id: str
    venue: str; sequence: str | None; conditions: tuple[str, ...]; provenance: Provenance
    def __post_init__(self):
        object.__setattr__(self,"provider_timestamp",_utc(self.provider_timestamp,"provider_timestamp"))
        object.__setattr__(self,"received_at",_utc(self.received_at,"received_at"))
        if self.provider_timestamp != self.provenance.provider_timestamp or self.received_at != self.provenance.received_at:
            raise MalformedMarketData("trade timestamps must match provenance")
        object.__setattr__(self,"price",_positive(self.price,"price")); object.__setattr__(self,"size",_positive(self.size,"size",zero=True))


@dataclass(frozen=True)
class Candle:
    instrument_id: str; timeframe: str; open_time: datetime; close_time: datetime
    open: Decimal; high: Decimal; low: Decimal; close: Decimal; volume: Decimal
    trade_count: int | None; provider_id: str; provider_timestamp: datetime
    received_at: datetime; complete: bool; provenance: Provenance
    def __post_init__(self):
        for name in ("open","high","low","close"): object.__setattr__(self,name,_positive(getattr(self,name),name))
        object.__setattr__(self,"volume",_positive(self.volume,"volume",zero=True))
        object.__setattr__(self,"open_time",_utc(self.open_time,"open_time")); object.__setattr__(self,"close_time",_utc(self.close_time,"close_time"))
        object.__setattr__(self,"provider_timestamp",_utc(self.provider_timestamp,"provider_timestamp")); object.__setattr__(self,"received_at",_utc(self.received_at,"received_at"))
        if self.provider_timestamp != self.provenance.provider_timestamp or self.received_at != self.provenance.received_at:
            raise MalformedMarketData("candle timestamps must match provenance")
        if self.close_time <= self.open_time or not (self.low <= self.open <= self.high and self.low <= self.close <= self.high): raise MalformedMarketData("impossible OHLC")


@dataclass(frozen=True)
class MarketStatus:
    instrument_id: str; status: MarketState; provider_timestamp: datetime
    received_at: datetime; provider_id: str; halt_status_available: bool; provenance: Provenance
    def __post_init__(self):
        object.__setattr__(self,"provider_timestamp",_utc(self.provider_timestamp,"provider_timestamp")); object.__setattr__(self,"received_at",_utc(self.received_at,"received_at"))
        if self.provider_timestamp != self.provenance.provider_timestamp or self.received_at != self.provenance.received_at:
            raise MalformedMarketData("status timestamps must match provenance")


@dataclass(frozen=True)
class OrderBookLevel: price: Decimal; size: Decimal
@dataclass(frozen=True)
class OrderBookSnapshot:
    instrument_id: str; bids: tuple[OrderBookLevel,...]; asks: tuple[OrderBookLevel,...]
    provider_timestamp: datetime; received_at: datetime; provider_id: str; sequence: str | None; provenance: Provenance


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str; event_type: str; schema_version: str; occurred_at: datetime
    provider_timestamp: datetime; server_timestamp: datetime; correlation_id: str; payload: object
    @classmethod
    def wrap(cls, event_type: str, payload, *, correlation_id=""):
        provenance=payload.provenance
        identity="|".join((provenance.provider_id,event_type,payload.instrument_id,provenance.provider_timestamp.isoformat(),str(getattr(payload,"sequence",None) or getattr(payload,"trade_id",None) or provenance.raw_message_hash or "")))
        return cls(hashlib.sha256(identity.encode()).hexdigest(),event_type,"1",provenance.provider_timestamp,provenance.provider_timestamp,datetime.now(UTC),correlation_id or str(uuid.uuid4()),payload)


class MarketDataProvider(Protocol):
    def health(self): ...
    def capabilities(self): ...
    def list_instruments(self): ...
    def get_quote(self, instrument_id): ...
    def get_quotes(self, instrument_ids): ...
    def get_trades(self, instrument_id, **kwargs): ...
    def get_candles(self, instrument_id, timeframe, **kwargs): ...
    def get_market_status(self, instrument_id): ...
    def subscribe_quotes(self, instrument_ids): ...
    def subscribe_trades(self, instrument_ids): ...
    def subscribe_candles(self, instrument_ids, timeframe): ...


def raw_hash(payload) -> str: return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()


def assess_freshness(provider_timestamp, received_at, now, *, degraded_ms, stale_ms):
    if provider_timestamp is None or received_at is None: return FreshnessState.UNAVAILABLE
    provider_age=max(0,(_utc(now,"now")-_utc(provider_timestamp,"provider_timestamp")).total_seconds()*1000)
    receive_age=max(0,(_utc(now,"now")-_utc(received_at,"received_at")).total_seconds()*1000)
    age=max(provider_age,receive_age)
    return FreshnessState.FRESH if age <= degraded_ms else FreshnessState.DEGRADED if age <= stale_ms else FreshnessState.STALE


def require_fresh(event, now, *, degraded_ms, stale_ms):
    state=assess_freshness(event.provider_timestamp,event.received_at,now,degraded_ms=degraded_ms,stale_ms=stale_ms)
    if state in {FreshnessState.STALE,FreshnessState.UNAVAILABLE}: raise StaleMarketData("MARKET_DATA_STALE")
    return state


class Deduplicator:
    def __init__(self, max_items=100_000): self.max_items=max_items; self._seen={}; self._order=[]
    def accept(self, envelope: EventEnvelope):
        if envelope.event_id in self._seen: return False
        self._seen[envelope.event_id]=True; self._order.append(envelope.event_id)
        if len(self._order)>self.max_items: self._seen.pop(self._order.pop(0),None)
        return True


class CandleAggregator:
    """Deterministic tick aggregator. Empty buckets are not fabricated."""
    def __init__(self, timeframe_seconds: int, *, late_tolerance_seconds=0):
        if timeframe_seconds <= 0: raise ValueError("timeframe_seconds must be positive")
        self.seconds=timeframe_seconds; self.late=timedelta(seconds=late_tolerance_seconds); self._ticks={}; self._finalized=set(); self._ids=set()
    def add(self, tick: TradeTick):
        identity=(tick.provider_id,tick.instrument_id,tick.trade_id or tick.sequence or raw_hash((tick.provider_timestamp,tick.price,tick.size)))
        if identity in self._ids: return None
        self._ids.add(identity)
        epoch=int(tick.provider_timestamp.timestamp()); start=epoch-(epoch%self.seconds)
        key=(tick.instrument_id,start)
        if key in self._finalized: return None
        self._ticks.setdefault(key,[]).append(tick); return key
    def close_through(self, watermark: datetime):
        watermark=_utc(watermark,"watermark")-self.late; closed=[]
        for key,ticks in sorted(list(self._ticks.items())):
            instrument_id,start=key; end=datetime.fromtimestamp(start+self.seconds,UTC)
            if end > watermark: continue
            ordered=sorted(ticks,key=lambda t:(t.provider_timestamp,t.trade_id or "",t.sequence or "")); prices=[t.price for t in ordered]
            last=ordered[-1]; provenance=replace(last.provenance,source_type="SERVER_AGGREGATE")
            closed.append(Candle(instrument_id,f"{self.seconds}s",datetime.fromtimestamp(start,UTC),end,prices[0],max(prices),min(prices),prices[-1],sum((t.size for t in ordered),Decimal(0)),len(ordered),last.provider_id,last.provider_timestamp,last.received_at,True,provenance))
            self._finalized.add(key); del self._ticks[key]
        return closed


class Backoff:
    def __init__(self, base=1.0, cap=60.0, jitter=0.2, rng=None): self.base=base; self.cap=cap; self.jitter=jitter; self.attempt=0; self.rng=rng or random.Random()
    def next_delay(self):
        delay=min(self.cap,self.base*(2**self.attempt)); self.attempt+=1
        return max(0,delay*self.rng.uniform(1-self.jitter,1+self.jitter))
    def stable(self): self.attempt=0


class RateLimitBudget:
    def __init__(self, capacity, window_seconds, clock=time.monotonic): self.capacity=capacity; self.window=window_seconds; self.clock=clock; self.remaining=capacity; self.reset_at=clock()+window_seconds; self.blocked_until=0.0
    def acquire(self):
        now=self.clock()
        if now < self.blocked_until: raise RateLimited("retry later")
        if now >= self.reset_at: self.remaining=self.capacity; self.reset_at=now+self.window
        if self.remaining <= 0: raise RateLimited("budget exhausted")
        self.remaining-=1
    def on_429(self, retry_after=None): self.blocked_until=self.clock()+max(0,float(retry_after if retry_after is not None else self.window))


class StreamIngestion:
    """Transport-neutral WebSocket lifecycle and sequence authority.

    A provider adapter owns socket I/O/auth payloads.  This controller owns the
    canonical lifecycle, heartbeat timeout, dedupe, gaps, and resubscription.
    """
    def __init__(self, subscriptions=(), *, idle_timeout_seconds=30, clock=time.monotonic):
        self.subscriptions=tuple(subscriptions); self.idle_timeout=idle_timeout_seconds; self.clock=clock
        self.state=ConnectionState.DISABLED; self.last_message_at=None; self.last_sequence=None
        self.gaps=0; self.reconnects=0; self.snapshot_required=False; self.deduplicator=Deduplicator()
    def enable(self): self.state=ConnectionState.DISCONNECTED
    def connecting(self): self.state=ConnectionState.CONNECTING
    def authenticating(self): self.state=ConnectionState.AUTHENTICATING
    def authenticated(self): self.state=ConnectionState.SUBSCRIBING; return self.subscriptions
    def subscribed(self): self.state=ConnectionState.LIVE; self.last_message_at=self.clock()
    def heartbeat(self): self.last_message_at=self.clock()
    def check_idle(self):
        if self.state == ConnectionState.LIVE and self.last_message_at is not None and self.clock()-self.last_message_at > self.idle_timeout:
            self.state=ConnectionState.DEGRADED; return False
        return True
    def accept(self, envelope: EventEnvelope, sequence: int | None=None):
        if self.state != ConnectionState.LIVE: return False
        self.last_message_at=self.clock()
        if sequence is not None and self.last_sequence is not None and sequence > self.last_sequence+1:
            self.gaps+=1; self.snapshot_required=True; self.state=ConnectionState.DEGRADED; return False
        if sequence is not None and self.last_sequence is not None and sequence <= self.last_sequence: return False
        if not self.deduplicator.accept(envelope): return False
        if sequence is not None: self.last_sequence=sequence
        return True
    def snapshot_restored(self, sequence=None):
        self.last_sequence=sequence; self.snapshot_required=False; self.state=ConnectionState.LIVE; self.last_message_at=self.clock()
    def disconnected(self): self.state=ConnectionState.BACKOFF; self.reconnects+=1


@dataclass(frozen=True)
class FailoverPolicy:
    instrument_id: str; data_type: str; primary: str; secondary: str | None
    failover_allowed: bool; max_switch_delay_ms: int; normalization_compatible: bool


class AuthoritySelector:
    def __init__(self, policy: FailoverPolicy): self.policy=policy; self.authoritative=None; self.state=FailoverState.NO_AUTHORITY
    def update(self, primary_live: bool, secondary_live: bool, *, elapsed_ms=0):
        if primary_live: self.authoritative=self.policy.primary; self.state=FailoverState.PRIMARY_LIVE
        elif not self.policy.failover_allowed or not self.policy.normalization_compatible or not secondary_live: self.authoritative=None; self.state=FailoverState.NO_AUTHORITY
        elif elapsed_ms < self.policy.max_switch_delay_ms: self.authoritative=None; self.state=FailoverState.FAILOVER_PENDING
        else: self.authoritative=self.policy.secondary; self.state=FailoverState.SECONDARY_LIVE
        return self.state
    def accepts(self, provider_id): return provider_id == self.authoritative


@dataclass(frozen=True)
class ReconciliationPolicy:
    absolute_tolerance: Decimal=Decimal("0"); relative_tolerance: Decimal=Decimal("0")
def reconcile(stream_value, snapshot_value, policy=ReconciliationPolicy()):
    a=Decimal(str(stream_value)); b=Decimal(str(snapshot_value)); difference=abs(a-b); scale=max(abs(a),abs(b),Decimal("1"))
    return {"match": difference <= policy.absolute_tolerance or difference/scale <= policy.relative_tolerance,"difference":difference}


TIMEFRAME_AUTHORITY={"1m":{"source":"provider-native aggregate","native_or_aggregated":"NATIVE","input_granularity":"1m","certified":True},"5m":{"source":"provider-native aggregate","native_or_aggregated":"NATIVE","input_granularity":"5m","certified":True},"15m":{"source":"provider-native aggregate","native_or_aggregated":"NATIVE","input_granularity":"15m","certified":True},"1h":{"source":"provider-native aggregate","native_or_aggregated":"NATIVE","input_granularity":"1h","certified":True},"4h":{"source":"provider-native aggregate","native_or_aggregated":"NATIVE","input_granularity":"4h","certified":True},"1d":{"source":"provider-native aggregate","native_or_aggregated":"NATIVE","input_granularity":"1d","certified":True},"5s":{"source":None,"native_or_aggregated":None,"input_granularity":None,"certified":False}}
FIVE_SECOND_AVAILABLE=False
