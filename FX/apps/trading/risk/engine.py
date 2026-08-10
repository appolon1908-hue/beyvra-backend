from dataclasses import dataclass
from decimal import Decimal

from apps.foundation.events import payload_hash


@dataclass(frozen=True)
class RiskResult:
    decision: str
    reason_codes: tuple[str, ...]
    inputs_hash: str
    policy_version: str = "spot-p0-v1"


class RiskEngine:
    def evaluate_order(self, inputs):
        reasons = []
        review_reasons = []
        if inputs.get("account_status", "ACTIVE") != "ACTIVE":
            reasons.append("ACCOUNT_RESTRICTED")
        if "simulation_eligible" in inputs and inputs.get("simulation_eligible") is not True:
            reasons.append("SIMULATION_NOT_AUTHORIZED")
        if inputs.get("kyc_status", "APPROVED") != "APPROVED":
            reasons.append("COMPLIANCE_RESTRICTED")
        if inputs.get("jurisdiction_allowed", True) is not True:
            reasons.append("JURISDICTION_RESTRICTED")
        if inputs.get("instrument_status", "ACTIVE") != "ACTIVE":
            reasons.append("INSTRUMENT_UNAVAILABLE")
        if inputs.get("market_status", "OPEN") != "OPEN":
            reasons.append("MARKET_CLOSED")
        if inputs.get("control_state", "ACTIVE") in {"HALTED", "MAINTENANCE"}:
            reasons.append("TRADING_HALTED")
        if inputs.get("market_data_stale"):
            reasons.append("MARKET_DATA_STALE")
        if inputs.get("provider_health") not in {None, "HEALTHY"}:
            reasons.append("PROVIDER_UNAVAILABLE")
        if not inputs.get("compliance_eligible", False):
            reasons.append("COMPLIANCE_RESTRICTED")
        quantity = Decimal(str(inputs.get("quantity", "0")))
        minimum_quantity = Decimal(str(inputs.get("min_quantity", "0")))
        maximum_quantity = Decimal(str(inputs.get("max_quantity", "Infinity")))
        if quantity <= 0 or quantity < minimum_quantity or quantity > maximum_quantity:
            reasons.append("QUANTITY_OUT_OF_RANGE")
        notional = Decimal(str(inputs.get("notional", "0")))
        minimum_notional = Decimal(str(inputs.get("min_notional", "0")))
        maximum_notional = Decimal(str(inputs.get("max_notional", "Infinity")))
        if notional <= 0 or notional < minimum_notional or notional > maximum_notional:
            reasons.append("NOTIONAL_OUT_OF_RANGE")
        if notional > Decimal(str(inputs.get("available_funds", "0"))):
            reasons.append("INSUFFICIENT_AVAILABLE_BALANCE")
        if notional + Decimal(str(inputs.get("daily_notional", "0"))) > Decimal(
            str(inputs.get("daily_notional_limit", "Infinity"))
        ):
            reasons.append("DAILY_NOTIONAL_LIMIT")
        if Decimal(str(inputs.get("daily_loss", "0"))) > Decimal(
            str(inputs.get("daily_loss_limit", "Infinity"))
        ):
            reasons.append("DAILY_LOSS_LIMIT")
        if Decimal(str(inputs.get("projected_position", quantity))) > Decimal(
            str(inputs.get("position_limit", "Infinity"))
        ):
            reasons.append("POSITION_LIMIT")
        reference_price = inputs.get("reference_price")
        order_price = inputs.get("order_price")
        price_band_percent = inputs.get("price_band_percent")
        if reference_price is not None and order_price is not None and price_band_percent is not None:
            reference = Decimal(str(reference_price))
            deviation = abs(Decimal(str(order_price)) - reference)
            if reference <= 0 or deviation > reference * Decimal(str(price_band_percent)) / Decimal("100"):
                reasons.append("PRICE_BAND_EXCEEDED")
        if inputs.get("manual_review_required", False):
            review_reasons.append("MANUAL_REVIEW")
        decision = "DENY" if reasons else "REVIEW" if review_reasons else "ALLOW"
        return RiskResult(decision, tuple(reasons or review_reasons), payload_hash(inputs))
