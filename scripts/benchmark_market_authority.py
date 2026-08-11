#!/usr/bin/env python3
"""Offline normalization/publication benchmark; performs no provider I/O."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"FX"))
from trade.market_authority import Deduplicator, EventEnvelope, Provenance, TradeTick  # noqa: E402


def percentile(values, q=.95): return sorted(values)[min(len(values)-1,int(len(values)*q))]
def run(instruments):
    now=datetime.now(timezone.utc); normalization=[]; publication=[]; dedupe=Deduplicator(max_items=instruments*2)
    for index in range(instruments):
        provider_time=now+timedelta(microseconds=index)
        start=time.perf_counter_ns()
        provenance=Provenance("fixture","trade",provider_time,provider_time,"WEBSOCKET",raw_message_hash=str(index))
        tick=TradeTick(f"FIXTURE-{index}",Decimal("100.01"),Decimal("1"),str(index),provider_time,provider_time,"fixture","FIXTURE",str(index),(),provenance)
        normalization.append((time.perf_counter_ns()-start)/1_000_000)
        start=time.perf_counter_ns(); assert dedupe.accept(EventEnvelope.wrap("market.trade.received.v1",tick)); publication.append((time.perf_counter_ns()-start)/1_000_000)
    return percentile(normalization),percentile(publication)


if __name__ == "__main__":
    for count in (100,500,1000):
        normalize_p95,stream_p95=run(count)
        print(f"instruments={count} normalization_p95_ms={normalize_p95:.4f} stream_p95_ms={stream_p95:.4f}")
