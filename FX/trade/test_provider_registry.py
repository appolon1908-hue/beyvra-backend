from django.test import SimpleTestCase

from trade.provider_cache import BoundedProviderCache
from trade.provider_registry import ProviderApproval, provider_readiness


class ProviderReadinessTests(SimpleTestCase):
    def test_missing_approval_and_credentials_are_blocked(self):
        record = ProviderApproval("fixture", "market", "staging", frozenset({"BTCUSDT"}), frozenset({"1m"}), "SYNTHETIC", False, False, False, None, None, None)
        self.assertEqual(provider_readiness(record)["status"], "BLOCKED")

    def test_cache_is_bounded_and_schema_scoped(self):
        cache = BoundedProviderCache(max_entries=1)
        cache.set("a", {"v": 1}, 60, "1")
        self.assertEqual(cache.get("a", "1"), {"v": 1})
        self.assertIsNone(cache.get("a", "2"))
        cache.set("b", {"v": 2}, 60, "1")
        self.assertIsNone(cache.get("a", "1"))
