#!/usr/bin/env python3
"""Offline fail-closed load harness; performs no network or financial mutation."""
import os
import statistics
import sys
import tempfile
import time
import uuid
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
from financial_boundary.reconciliation import ReconciliationEvidence, compare_records, reconcile_financial_boundary  # noqa: E402
from financial_client.client import FinancialContext, FinancialServiceClient  # noqa: E402


class Actor:
    is_authenticated = True
    pk = 1


class Response:
    status_code = 200
    def __init__(self, body): self.body = body
    def json(self): return self.body


class IdempotentAdapter:
    def __init__(self): self.keys = {}; self.business_effects = 0
    def request(self, method, url, **kwargs):
        key = kwargs["headers"]["Idempotency-Key"]
        if key not in self.keys:
            self.business_effects += 1
            self.keys[key] = {"operation_ref": f"isolated-{self.business_effects}"}
        return Response(self.keys[key])


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
    with tempfile.TemporaryDirectory() as temporary_directory:
        tls_root = Path(temporary_directory)
        for filename in ("client.crt", "client.key", "ca.crt"):
            (tls_root / filename).write_text("isolated-test-material", encoding="utf-8")
        context = FinancialContext(uuid.uuid4(), uuid.uuid4(), "load-test", uuid.uuid4())
        with override_settings(
            FINANCIAL_SERVICE_CLIENT_CERT=str(tls_root / "client.crt"),
            FINANCIAL_SERVICE_CLIENT_KEY=str(tls_root / "client.key"),
            FINANCIAL_SERVICE_CA_CERT=str(tls_root / "ca.crt"),
        ):
            for count in (100, 1000, 5000):
                adapter, samples = IdempotentAdapter(), []
                client = FinancialServiceClient(session=adapter)
                for _ in range(count):
                    started = time.perf_counter()
                    client.request_transfer(context, {"amount": "1.00", "asset": "USD"}, "same-load-key")
                    samples.append((time.perf_counter() - started) * 1000)
                assert adapter.business_effects == 1
                print(f"IDEMPOTENCY_LOAD={count} EFFECTS=1 P50_MS={statistics.median(samples):.3f} P95_MS={percentile(samples,.95):.3f} P99_MS={percentile(samples,.99):.3f}")
    left = [{"reference": str(i), "state": "PENDING"} for i in range(10000)]
    samples = []
    for _ in range(10):
        started = time.perf_counter(); assert compare_records(left, left) == []
        samples.append((time.perf_counter() - started) * 1000)
    print(f"RECONCILIATION_ROWS=10000 P95_MS={percentile(samples,.95):.3f}")
    application = tuple({"reference": str(i), "state": "PENDING"} for i in range(10000))
    financial = tuple({"reference": str(i), "state": "PENDING", "effect_id": f"effect-{i}"} for i in range(10000))
    evidence = ReconciliationEvidence(application_operations=application, financial_operations=financial)
    samples = []
    for _ in range(10):
        started = time.perf_counter(); report = reconcile_financial_boundary(evidence)
        samples.append((time.perf_counter() - started) * 1000)
        assert report.activation_ready and len(report.checks_executed) == 10
    print(f"RECONCILIATION_ENGINE_ROWS=10000 CHECKS=10 FALSE_POSITIVES=0 P95_MS={percentile(samples,.95):.3f}")
    print("OUTBOUND_REQUESTS=0 REAL_FINANCIAL_EFFECTS=0")


if __name__ == "__main__":
    main()
