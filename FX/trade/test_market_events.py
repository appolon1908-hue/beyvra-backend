from django.test import SimpleTestCase

from trade.market_events import MarketEvent, SequenceTracker


class MarketEventSequenceTests(SimpleTestCase):
    def event(self, event_id, sequence):
        return MarketEvent(event_id, "1", "market.BTCUSD.tick", sequence, "2026-08-06T00:00:00Z", {})

    def test_duplicate_out_of_order_and_gap(self):
        tracker = SequenceTracker(max_replay=2)
        self.assertEqual(tracker.accept(self.event("e1", 1)), "ACCEPTED")
        self.assertEqual(tracker.accept(self.event("e1", 1)), "DUPLICATE")
        self.assertEqual(tracker.accept(self.event("e0", 0)), "OUT_OF_ORDER")
        self.assertEqual(tracker.accept(self.event("e4", 4)), "SNAPSHOT_REQUIRED")
