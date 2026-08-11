#!/usr/bin/env python3
"""Offline fail-closed load harness; performs no network or financial mutation."""
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "FX"
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FX.financial_test_settings")

import django  # noqa: E402
django.setup()
from django.test import override_settings  # noqa: E402
from django.conf import settings  # noqa: E402
from rest_framework.test import APIRequestFactory, force_authenticate  # noqa: E402
from financial_boundary.views import WithdrawalView  # noqa: E402
from financial_boundary.reconciliation import compare_records  # noqa: E402


class Actor:
    is_authenticated = True
    pk = 1


def percentile(values, percent):
    return sorted(values)[max(0, int(len(values) * percent) - 1)]


def main():
    WithdrawalView.throttle_classes = ()
    factory, view = APIRequestFactory(), WithdrawalView.as_view()
    test_rest = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}
    with override_settings(REAL_MONEY_ENABLED=False, REAL_WITHDRAWALS_ENABLED=False, REST_FRAMEWORK=test_rest):
        for count in (100, 1000, 5000):
            samples = []
            for _ in range(count):
                request = factory.post("/api/v1/withdrawals/", {}, format="json", HTTP_IDEMPOTENCY_KEY="same-key")
                force_authenticate(request, user=Actor())
                started = time.perf_counter()
                response = view(request)
                samples.append((time.perf_counter() - started) * 1000)
                assert response.data["code"] == "FEATURE_DISABLED"
            print(f"LOAD={count} P50_MS={statistics.median(samples):.3f} P95_MS={percentile(samples,.95):.3f} P99_MS={percentile(samples,.99):.3f}")
    left = [{"reference": str(i), "state": "PENDING"} for i in range(10000)]
    samples = []
    for _ in range(10):
        started = time.perf_counter(); assert compare_records(left, left) == []
        samples.append((time.perf_counter() - started) * 1000)
    print(f"RECONCILIATION_ROWS=10000 P95_MS={percentile(samples,.95):.3f}")
    print("OUTBOUND_REQUESTS=0 REAL_FINANCIAL_EFFECTS=0")


if __name__ == "__main__":
    main()
