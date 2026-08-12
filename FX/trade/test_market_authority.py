from datetime import datetime, timedelta, timezone
from decimal import Decimal
import random

from django.test import SimpleTestCase

from .market_authority import (
    AmbiguousSymbol, AuthoritySelector, Backoff, CandleAggregator, Deduplicator,
    EventEnvelope, FailoverPolicy, FailoverState, FIVE_SECOND_AVAILABLE,
    FreshnessState, Instrument, InstrumentRegistry, MalformedMarketData,
    Provenance, Quote, RateLimitBudget, RateLimited, ReconciliationPolicy,
    StaleMarketData, StreamIngestion, TradeTick, assess_freshness, reconcile, require_fresh,
)

UTC=timezone.utc
NOW=datetime(2026,8,11,12,0,tzinfo=UTC)


def provenance(at=NOW, *, message="trade"):
    return Provenance("fixture",message,at,at+timedelta(milliseconds=2),"WEBSOCKET",raw_message_hash="abc")


def tick(at, price, size="1", trade_id=None, sequence=None):
    return TradeTick("BTC-USD",Decimal(price),Decimal(size),trade_id,at,at+timedelta(milliseconds=2),"fixture","TEST",sequence,(),provenance(at))


class CanonicalContractTests(SimpleTestCase):
    def test_quote_never_fabricates_bid_ask_and_marks_crossed_quote_suspect(self):
        last_only=Quote("BTC-USD",None,None,None,None,Decimal("10"),NOW,NOW+timedelta(milliseconds=2),"fixture",None,False,False,provenance(message="quote"))
        self.assertIsNone(last_only.bid); self.assertIsNone(last_only.ask)
        crossed=Quote("BTC-USD",Decimal("11"),Decimal("10"),1,1,None,NOW,NOW+timedelta(milliseconds=2),"fixture","1",False,False,provenance(message="quote"))
        self.assertTrue(crossed.suspect)

    def test_invalid_values_and_impossible_mapping_are_rejected(self):
        with self.assertRaises(MalformedMarketData): tick(NOW,"-1")
        a=Instrument("A","A","A","EQUITY",None,None,"X",{"p":"SAME"},"ACTIVE",2,2,"UTC")
        b=Instrument("B","B","B","EQUITY",None,None,"X",{"p":"SAME"},"ACTIVE",2,2,"UTC")
        with self.assertRaises(AmbiguousSymbol): InstrumentRegistry([a,b])

    def test_contract_timestamps_cannot_diverge_from_provenance(self):
        with self.assertRaisesRegex(MalformedMarketData,"timestamps must match provenance"):
            Quote("BTC-USD",Decimal("9"),Decimal("10"),None,None,None,NOW+timedelta(seconds=1),NOW,"fixture",None,False,False,provenance(message="quote"))

    def test_freshness_uses_both_provider_and_receive_clocks(self):
        self.assertEqual(assess_freshness(NOW,NOW,NOW+timedelta(milliseconds=50),degraded_ms=100,stale_ms=500),FreshnessState.FRESH)
        self.assertEqual(assess_freshness(NOW,NOW,NOW+timedelta(milliseconds=300),degraded_ms=100,stale_ms=500),FreshnessState.DEGRADED)
        event=tick(NOW,"10")
        with self.assertRaisesRegex(StaleMarketData,"MARKET_DATA_STALE"): require_fresh(event,NOW+timedelta(seconds=2),degraded_ms=100,stale_ms=500)

    def test_deterministic_identity_deduplicates_duplicate_inputs(self):
        event=EventEnvelope.wrap("market.trade.received.v1",tick(NOW,"10",trade_id="opaque"))
        duplicate=EventEnvelope.wrap("market.trade.received.v1",tick(NOW,"10",trade_id="opaque"))
        dedupe=Deduplicator(); self.assertTrue(dedupe.accept(event)); self.assertFalse(dedupe.accept(duplicate))


class AggregationTests(SimpleTestCase):
    def test_out_of_order_ticks_have_deterministic_ohlcv_and_duplicates_drop(self):
        aggregator=CandleAggregator(5)
        aggregator.add(tick(NOW+timedelta(seconds=3),"12","2",trade_id="3"))
        aggregator.add(tick(NOW+timedelta(seconds=1),"10","1",trade_id="1"))
        aggregator.add(tick(NOW+timedelta(seconds=2),"9","3",trade_id="2"))
        aggregator.add(tick(NOW+timedelta(seconds=2),"9","3",trade_id="2"))
        candles=aggregator.close_through(NOW+timedelta(seconds=5))
        self.assertEqual(len(candles),1)
        candle=candles[0]
        self.assertEqual((candle.open,candle.high,candle.low,candle.close,candle.volume,candle.trade_count),(Decimal("10"),Decimal("12"),Decimal("9"),Decimal("12"),Decimal("6"),3))
        self.assertTrue(candle.complete)

    def test_finalized_candle_is_not_rewound_and_empty_interval_not_created(self):
        aggregator=CandleAggregator(5); aggregator.add(tick(NOW+timedelta(seconds=1),"10",trade_id="1")); aggregator.close_through(NOW+timedelta(seconds=5))
        self.assertIsNone(aggregator.add(tick(NOW+timedelta(seconds=2),"99",trade_id="late")))
        self.assertEqual(aggregator.close_through(NOW+timedelta(seconds=20)),[])

    def test_aggregator_does_not_activate_five_seconds(self): self.assertFalse(FIVE_SECOND_AVAILABLE)


class ControlTests(SimpleTestCase):
    def test_stream_reconnect_resubscribe_idle_and_sequence_recovery(self):
        clock=[0.0]; stream=StreamIngestion(("Q.BTC",),idle_timeout_seconds=10,clock=lambda:clock[0])
        stream.enable(); stream.connecting(); stream.authenticating(); self.assertEqual(stream.authenticated(),("Q.BTC",)); stream.subscribed()
        event=EventEnvelope.wrap("market.trade.received.v1",tick(NOW,"10",trade_id="1"))
        self.assertTrue(stream.accept(event,1)); self.assertFalse(stream.accept(event,1))
        gap=EventEnvelope.wrap("market.trade.received.v1",tick(NOW+timedelta(seconds=1),"11",trade_id="3"))
        self.assertFalse(stream.accept(gap,3)); self.assertTrue(stream.snapshot_required)
        stream.snapshot_restored(3); clock[0]=11; self.assertFalse(stream.check_idle())
        stream.disconnected(); self.assertEqual(stream.reconnects,1)

    def test_bounded_backoff_with_jitter_and_stable_reset(self):
        backoff=Backoff(base=1,cap=4,jitter=.1,rng=random.Random(7)); values=[backoff.next_delay() for _ in range(5)]
        self.assertTrue(all(0 <= value <= 4.4 for value in values)); self.assertGreater(values[2],values[0]); backoff.stable(); self.assertLess(backoff.next_delay(),1.1)

    def test_rate_limit_respects_retry_after(self):
        clock=[0.0]; budget=RateLimitBudget(1,60,clock=lambda:clock[0]); budget.acquire()
        with self.assertRaises(RateLimited): budget.acquire()
        budget.on_429(12); clock[0]=11
        with self.assertRaises(RateLimited): budget.acquire()
        clock[0]=61; budget.acquire()

    def test_failover_is_observable_and_split_brain_is_prevented(self):
        selector=AuthoritySelector(FailoverPolicy("BTC-USD","QUOTE","primary","secondary",True,1000,True))
        self.assertEqual(selector.update(False,True,elapsed_ms=500),FailoverState.FAILOVER_PENDING); self.assertIsNone(selector.authoritative)
        self.assertEqual(selector.update(False,True,elapsed_ms=1000),FailoverState.SECONDARY_LIVE)
        self.assertTrue(selector.accepts("secondary")); self.assertFalse(selector.accepts("primary"))
        self.assertEqual(selector.update(True,True),FailoverState.PRIMARY_LIVE); self.assertTrue(selector.accepts("primary")); self.assertFalse(selector.accepts("secondary"))

    def test_snapshot_stream_reconciliation_uses_explicit_tolerance(self):
        self.assertTrue(reconcile("100","100.01",ReconciliationPolicy(Decimal("0.02"),Decimal("0")))["match"])
        self.assertFalse(reconcile("100","101",ReconciliationPolicy(Decimal("0.02"),Decimal("0.001")))["match"])
