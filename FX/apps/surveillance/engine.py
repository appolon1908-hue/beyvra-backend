import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.trading.models import TradingOrder

from .models import SurveillanceRule, TradingRestriction
from .observability import EVALUATIONS, LATENCY, STP


@dataclass(frozen=True)
class Finding:
    event_type: str
    severity: str
    score: Decimal
    rule_id: str
    rule_version: int
    policy_version: str
    evidence_safe: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SurveillanceDecision:
    decision: str
    reason_codes: tuple[str, ...]
    findings: tuple[Finding, ...]
    policy_version: str


def evidence_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _rule(event_type, at=None):
    at = at or timezone.now()
    return SurveillanceRule.objects.filter(event_type=event_type, enabled=True, effective_from__lte=at).filter(Q(effective_to__isnull=True) | Q(effective_to__gt=at)).order_by("-version").first()


def _finding(rule, score, evidence):
    return Finding(rule.event_type, rule.severity, Decimal(str(score)), str(rule.id), rule.version, rule.policy_version, evidence)


def active_restrictions(*, tenant_ref, account_ref, instrument_id, side, asset_class="", venue="", jurisdiction="", at=None):
    at = at or timezone.now()
    refs = Q(scope_type="TENANT", scope_ref=tenant_ref) | Q(scope_type="ACCOUNT", scope_ref=account_ref) | Q(scope_type="INSTRUMENT", scope_ref=instrument_id)
    if asset_class:
        refs |= Q(scope_type="ASSET_CLASS", scope_ref=asset_class)
    if venue:
        refs |= Q(scope_type="VENUE", scope_ref=venue)
    if jurisdiction:
        refs |= Q(scope_type="JURISDICTION", scope_ref=jurisdiction)
    restrictions = TradingRestriction.objects.filter(tenant_ref=tenant_ref, status="ACTIVE", effective_from__lte=at).filter(Q(effective_to__isnull=True) | Q(effective_to__gt=at)).filter(refs)
    hard = {"BLOCK_NEW_ORDERS", "BLOCK_INSTRUMENT", "BLOCK_ASSET_CLASS", "BLOCK_VENUE"}
    return [row for row in restrictions if row.restriction_type in hard or row.restriction_type == f"BLOCK_{side}S" or row.restriction_type in {"CANCEL_ONLY", "CLOSE_ONLY", "REVIEW_REQUIRED"}]


class SelfTradePreventionEngine:
    ACTIVE_STATES = ("PENDING", "ACCEPTED", "OPEN", "PARTIALLY_FILLED")

    @staticmethod
    def _crosses(incoming, resting):
        if incoming["order_type"] == "MARKET" or resting.order_type == "MARKET":
            return True
        incoming_price = incoming.get("limit_price") or incoming.get("price")
        resting_price = resting.limit_price
        if incoming_price is None or resting_price is None:
            return True
        return incoming_price >= resting_price if incoming["side"] == "BUY" else incoming_price <= resting_price

    def evaluate(self, *, tenant_ref, account_ref, payload):
        opposite = "SELL" if payload["side"] == "BUY" else "BUY"
        rows = TradingOrder.objects.filter(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=payload["instrument_id"], side=opposite, state__in=self.ACTIVE_STATES, simulation=True)
        return next((row for row in rows if self._crosses(payload, row)), None)


class SurveillanceEngine:
    POLICY_VERSION = "surveillance-2026-08-v1"

    def evaluate_order(self, *, tenant_ref, account_ref, payload, asset_class="", venue="", jurisdiction="", market_data_stale=False):
        started = time.perf_counter()
        def finish(result):
            EVALUATIONS.labels("PRETRADE", result.decision).inc()
            LATENCY.labels(result.decision).observe(time.perf_counter() - started)
            return result
        if not getattr(settings, "SURVEILLANCE_ENABLED", True):
            return finish(SurveillanceDecision("DENY", ("SURVEILLANCE_TEMPORARILY_UNAVAILABLE",), (), self.POLICY_VERSION))
        restrictions = active_restrictions(tenant_ref=tenant_ref, account_ref=account_ref, instrument_id=payload["instrument_id"], side=payload["side"], asset_class=asset_class, venue=venue, jurisdiction=jurisdiction)
        if restrictions:
            rule = _rule("RESTRICTED_INSTRUMENT_ATTEMPT")
            finding = _finding(rule, "1", {"restriction_types": sorted({r.restriction_type for r in restrictions})}) if rule else None
            review_only = all(r.restriction_type == "REVIEW_REQUIRED" for r in restrictions)
            return finish(SurveillanceDecision("REVIEW" if review_only else "DENY", ("ACCOUNT_REVIEW_REQUIRED" if review_only else "TRADING_NOT_AVAILABLE",), tuple(v for v in (finding,) if v), self.POLICY_VERSION))
        if getattr(settings, "SELF_TRADE_PREVENTION_ENABLED", True):
            resting = SelfTradePreventionEngine().evaluate(tenant_ref=tenant_ref, account_ref=account_ref, payload=payload)
            if resting:
                STP.labels("prevented").inc()
                rule = _rule("SELF_TRADE_ATTEMPT")
                finding = _finding(rule, "1", {"resting_order_ref": str(resting.id), "mode": "REJECT_NEW"}) if rule else None
                return finish(SurveillanceDecision("DENY", ("ORDER_REJECTED",), tuple(v for v in (finding,) if v), self.POLICY_VERSION))
        price_rule = _rule("PRICE_DEVIATION_ORDER")
        if price_rule and not market_data_stale and payload.get("limit_price") is not None:
            reference = Decimal(str(payload["price"]))
            deviation = abs(Decimal(str(payload["limit_price"])) - reference) / reference
            if deviation >= Decimal(str(price_rule.parameters_json_safe.get("deviation_ratio", "0.1"))):
                finding = _finding(price_rule, min(deviation, Decimal("1")), {"deviation_ratio": str(deviation), "reference_source": "canonical_market_authority"})
                return finish(SurveillanceDecision("REVIEW", ("ACCOUNT_REVIEW_REQUIRED",), (finding,), self.POLICY_VERSION))
        return finish(SurveillanceDecision("ALLOW", (), (), self.POLICY_VERSION))

    def evaluate_window(self, events):
        """Deterministic indicator extraction over sanitized chronological events."""
        findings = []
        if not events:
            return findings
        ordered = sorted(events, key=lambda row: row["at"])
        placed = [e for e in ordered if e["kind"] == "ORDER"]
        cancelled = [e for e in ordered if e["kind"] == "CANCEL"]
        trades = [e for e in ordered if e["kind"] == "TRADE"]
        cancel_rule = _rule("EXCESSIVE_CANCEL_PATTERN")
        if cancel_rule and len(placed) >= int(cancel_rule.parameters_json_safe.get("minimum_orders", 5)):
            ratio = Decimal(len(cancelled)) / Decimal(len(placed))
            if ratio >= Decimal(str(cancel_rule.parameters_json_safe.get("cancel_ratio", "0.8"))):
                findings.append(_finding(cancel_rule, ratio, {"orders": len(placed), "cancels": len(cancelled), "cancel_ratio": str(ratio)}))
        flip_rule = _rule("RAPID_ORDER_FLIP")
        if flip_rule:
            seconds = int(flip_rule.parameters_json_safe.get("window_seconds", 30))
            for first, second in zip(placed, placed[1:]):
                if first["side"] != second["side"] and second["at"] - first["at"] <= timedelta(seconds=seconds):
                    findings.append(_finding(flip_rule, "0.7", {"window_seconds": seconds, "direction": f'{first["side"]}_TO_{second["side"]}'})); break
        wash_rule = _rule("WASH_TRADE_PATTERN")
        if wash_rule and len(trades) >= int(wash_rule.parameters_json_safe.get("minimum_trades", 4)):
            buys = sum(Decimal(str(e["quantity"])) for e in trades if e["side"] == "BUY")
            sells = sum(Decimal(str(e["quantity"])) for e in trades if e["side"] == "SELL")
            total = buys + sells
            if total and abs(buys - sells) / total <= Decimal(str(wash_rule.parameters_json_safe.get("max_net_ratio", "0.1"))):
                findings.append(_finding(wash_rule, "0.8", {"trade_count": len(trades), "net_ratio": str(abs(buys - sells) / total)}))
        spoof_rule = _rule("SPOOFING_INDICATOR")
        if spoof_rule and any(e.get("large", False) and e.get("rapid", False) for e in cancelled) and trades:
            findings.append(_finding(spoof_rule, "0.75", {"rapid_large_cancels": sum(bool(e.get("large") and e.get("rapid")) for e in cancelled)}))
        layering_rule = _rule("LAYERING_INDICATOR")
        levels = {e.get("price") for e in cancelled if e.get("rapid", False)}
        if layering_rule and len(levels - {None}) >= int(layering_rule.parameters_json_safe.get("minimum_levels", 3)) and trades:
            findings.append(_finding(layering_rule, "0.8", {"cancelled_price_levels": len(levels - {None})}))
        rate_rule = _rule("ORDER_RATE_ANOMALY")
        if rate_rule and len(placed) >= int(rate_rule.parameters_json_safe.get("orders_per_window", 20)):
            findings.append(_finding(rate_rule, "0.7", {"orders": len(placed), "window_seconds": int((ordered[-1]["at"] - ordered[0]["at"]).total_seconds())}))
        return findings
