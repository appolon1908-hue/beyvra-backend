from django.test import SimpleTestCase

from real_wallet.stream import StreamCursor, event_envelope, validate_resume


class StreamProtocolTests(SimpleTestCase):
    def test_resume_states(self):
        self.assertEqual(validate_resume(StreamCursor("wallet.balance", 2), 4), "REPLAY_AVAILABLE")
        self.assertEqual(validate_resume(StreamCursor("wallet.balance", 4), 4), "UP_TO_DATE")
        self.assertEqual(validate_resume(StreamCursor("wallet.balance", 5), 4), "SNAPSHOT_REQUIRED")

    def test_envelope_is_versioned(self):
        envelope = event_envelope(event_id="evt", event_type="wallet.balance.updated", channel="wallet.balance", subject="wallet/w1", sequence=1, occurred_at="2026-01-01T00:00:00Z", correlation_id="corr", data={})
        self.assertEqual(envelope["version"], "1")
        self.assertEqual(envelope["sequence"], 1)
