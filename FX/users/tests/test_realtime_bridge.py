from django.test import SimpleTestCase

from users.management.commands.realtime_v2_bridge import _normalize_envelope


class RealtimeBridgeEnvelopeTests(SimpleTestCase):
    def test_canonical_non_trading_event_with_channel_is_forwarded(self):
        envelope = {
            "event_type": "compliance.profile.updated.v1",
            "schema_version": 1,
            "channel": "private.account-1.compliance",
            "payload": {"account_ref": "account-1"},
        }

        normalized = _normalize_envelope("COMPLIANCE_EVENTS", envelope, 42)

        self.assertEqual(normalized["type"], "event")
        self.assertEqual(normalized["event_type"], envelope["event_type"])
        self.assertEqual(normalized["channel"], envelope["channel"])
        self.assertEqual(normalized["sequence"], 42)
        self.assertEqual(normalized["data"], envelope["payload"])

    def test_event_without_public_channel_is_rejected(self):
        self.assertIsNone(
            _normalize_envelope(
                "VALUATION_EVENTS",
                {"event_type": "valuation.updated.v1", "payload": {}},
                1,
            )
        )
