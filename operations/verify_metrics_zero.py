#!/usr/bin/env python3
"""Certify fail-closed Beyvra metrics from private Prometheus snapshots."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

_SAMPLE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>[^}]*)\})?\s+"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|NaN|[+-]Inf)"
    r"(?:\s+\d+)?$"
)
_LABEL = re.compile(r'(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<value>(?:\\.|[^"\\])*)"')

LIVE_EFFECTS = (
    "broker_order_create",
    "broker_order_cancel",
    "custody_provider",
    "payment_provider",
    "transactional_email",
)
LIVE_RESULTS = ("attempt", "success", "failure")
DISABLED_FLAGS = (
    "real_trading_enabled",
    "external_execution_enabled",
    "real_money_enabled",
    "real_deposits_enabled",
    "real_withdrawals_enabled",
    "real_internal_transfers_enabled",
    "live_broker_routing_enabled",
    "fix_live_session_enabled",
    "payments_enabled",
    "transactional_email_enabled",
    "welcome_email_enabled",
    "simulated_trading_enabled",
    "realtime_v2_v1_fallback_enabled",
)


def _unescape(value: str) -> str:
    return (
        value.replace(r"\\", "\0")
        .replace(r'\"', '"')
        .replace(r"\n", "\n")
        .replace("\0", "\\")
    )


def parse_metrics(path: Path) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
    samples: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE.match(line)
        if not match:
            # Prometheus exemplars and histogram syntax outside the safety
            # families are irrelevant to this bounded certification parser.
            continue
        labels_text = match.group("labels") or ""
        labels = tuple(
            sorted(
                (label.group("name"), _unescape(label.group("value")))
                for label in _LABEL.finditer(labels_text)
            )
        )
        value = float(match.group("value"))
        if not math.isfinite(value):
            raise ValueError(f"non-finite metric at {path}:{number}")
        samples[(match.group("name"), labels)] = value
    return samples


def get_samples(
    samples: dict[tuple[str, tuple[tuple[str, str], ...]], float],
    name: str,
    **labels: str,
) -> list[float]:
    expected = tuple(sorted(labels.items()))
    values: list[float] = []
    for (sample_name, sample_labels), value in samples.items():
        if sample_name != name:
            continue
        sample_dict = dict(sample_labels)
        if all(sample_dict.get(key) == label for key, label in expected):
            values.append(value)
    return values


def require_value(
    values: list[float],
    expected: float,
) -> bool:
    return bool(values) and all(value == expected for value in values)


def evaluate(path: Path) -> tuple[list[dict[str, object]], dict[str, float]]:
    samples = parse_metrics(path)
    checks: list[dict[str, object]] = []
    selected: dict[str, float] = {}

    deployment_values = get_samples(
        samples,
        "beyvra_safety_flag_enabled",
        flag="deployment_read_only",
    )
    checks.append(
        {
            "name": "deployment_read_only_metric",
            "values": deployment_values,
            "result": (
                "PASS" if require_value(deployment_values, 1) else "FAIL"
            ),
        }
    )
    if deployment_values:
        selected["safety:deployment_read_only"] = sum(deployment_values)

    for flag in DISABLED_FLAGS:
        values = get_samples(
            samples,
            "beyvra_safety_flag_enabled",
            flag=flag,
        )
        checks.append(
            {
                "name": f"safety_flag:{flag}",
                "values": values,
                "result": "PASS" if require_value(values, 0) else "FAIL",
            }
        )
        if values:
            selected[f"safety:{flag}"] = sum(values)

    for effect in LIVE_EFFECTS:
        for result in LIVE_RESULTS:
            values = get_samples(
                samples,
                "beyvra_live_effects_total",
                effect=effect,
                result=result,
            )
            checks.append(
                {
                    "name": f"live_effect:{effect}:{result}",
                    "values": values,
                    "result": "PASS" if require_value(values, 0) else "FAIL",
                }
            )
            if values:
                selected[f"effect:{effect}:{result}"] = sum(values)

    return checks, selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    before_checks, before_values = evaluate(args.before)
    after_checks, after_values = evaluate(args.after)
    keys_match = set(before_values) == set(after_values)
    unchanged = keys_match and all(
        before_values[key] == after_values[key] for key in before_values
    )

    checks = [
        {"phase": "before", **check} for check in before_checks
    ] + [{"phase": "after", **check} for check in after_checks]
    checks.extend(
        [
            {
                "name": "required_metric_series_complete",
                "result": "PASS" if keys_match else "FAIL",
            },
            {
                "name": "safety_and_live_effect_metrics_unchanged",
                "result": "PASS" if unchanged else "FAIL",
            },
        ]
    )
    overall = all(check["result"] == "PASS" for check in checks)
    evidence = {
        "schema_version": 1,
        "before": str(args.before),
        "after": str(args.after),
        "checks": checks,
        "overall": "PASS" if overall else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, separators=(",", ":")))
    return 0 if overall else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "overall": "FAIL",
                    "failure_category": type(exc).__name__,
                }
            )
        )
        raise SystemExit(1)
