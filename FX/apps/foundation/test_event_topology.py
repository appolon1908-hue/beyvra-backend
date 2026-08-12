from django.test import SimpleTestCase

from .publisher import subject_for


class EventTopologyTests(SimpleTestCase):
    def test_canonical_domain_subject_is_unchanged(self):
        self.assertEqual(subject_for("post_trade.settlement.pending.v1"), "post_trade.settlement.pending.v1")

    def test_legacy_application_subject_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "NON_CANONICAL_EVENT_SUBJECT"):
            subject_for("application.order.created")

    def test_unqualified_event_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "NON_CANONICAL_EVENT_SUBJECT"):
            subject_for("order_created")
