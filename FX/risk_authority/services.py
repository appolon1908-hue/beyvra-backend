from dataclasses import dataclass
from decimal import Decimal
from django.db.models import Q
from django.utils import timezone
from .models import CollateralPolicy, ExposureLimit, MarginPolicy


def _decimal(value, name):
    if not isinstance(value, Decimal) or not value.is_finite(): raise ValueError(f"{name} must be Decimal")
    return value


class MarginRequirementService:
    @staticmethod
    def calculate(*, policy, side, quantity, price):
        quantity=_decimal(quantity,"quantity"); price=_decimal(price,"price")
        if quantity <= 0 or price <= 0: raise ValueError("positive quantity and price required")
        notional=quantity*price
        rate=policy.short_margin_rate if side=="SELL" and policy.short_margin_rate is not None else policy.initial_margin_rate
        return {"notional":notional,"initial_margin_required":notional*rate,"maintenance_margin_required":notional*policy.maintenance_margin_rate,"policy_version":policy.policy_version,"simulation":True}
    calculate_initial=calculate; calculate_maintenance=calculate; calculate_order_impact=calculate


class CollateralService:
    @staticmethod
    def preview(*, policy, quantity, price, fresh=True):
        quantity=_decimal(quantity,"quantity"); price=_decimal(price,"price")
        if quantity < 0 or price <= 0: raise ValueError("invalid collateral value")
        gross=quantity*price; eligible=policy.eligible and fresh
        return {"gross_value":gross,"haircut_rate":policy.haircut_rate,"eligible_value":gross*(Decimal("1")-policy.haircut_rate) if eligible else Decimal("0"),"valuation_currency":policy.valuation_currency,"quality_state":"ELIGIBLE" if eligible else ("STALE" if not fresh else "INELIGIBLE"),"simulation":True}
    calculate_eligible_collateral=preview; calculate_haircut=preview; get_collateral_positions=preview; validate_asset=preview


class BuyingPowerService:
    @staticmethod
    def calculate_snapshot(*, equity, eligible_collateral, initial_margin_used, reservations):
        values=[_decimal(x,"value") for x in (equity,eligible_collateral,initial_margin_used,reservations)]
        available=max(values[0]+values[1]-values[2]-values[3],Decimal("0"))
        return {"equity":equity,"eligible_collateral":eligible_collateral,"initial_margin_used":initial_margin_used,"open_order_reservations":reservations,"available_buying_power":available,"simulation":True}
    @staticmethod
    def calculate_order_impact(snapshot, required):
        required=_decimal(required,"required"); after=snapshot["available_buying_power"]-required
        return {"current_buying_power":snapshot["available_buying_power"],"required_margin":required,"post_order_buying_power":max(after,Decimal("0")),"allowed":after>=0,"reason_codes":[] if after>=0 else ["INSUFFICIENT_COLLATERAL"],"simulation":True}
    can_accept_order=calculate_order_impact


class ExposureService:
    @staticmethod
    def evaluate_order(*, current_gross, order_notional, limits):
        post=_decimal(current_gross,"current")+abs(_decimal(order_notional,"order")); applicable=[x for x in limits if x.limit_type=="MAX_GROSS_NOTIONAL"]
        ceiling=min((x.limit_value for x in applicable),default=None); allowed=ceiling is not None and post<=ceiling
        return {"current":current_gross,"order_impact":abs(order_notional),"post_order":post,"limit":ceiling,"allowed":allowed,"reason_codes":[] if allowed else ["EXPOSURE_LIMIT"]}
    calculate_snapshot=evaluate_order; get_active_limits=evaluate_order; get_limit_utilization=evaluate_order


class MarginHealthService:
    @staticmethod
    def calculate(*, equity, maintenance):
        equity=_decimal(equity,"equity"); maintenance=_decimal(maintenance,"maintenance")
        excess=equity-maintenance; ratio=equity/maintenance if maintenance>0 else Decimal("999")
        state="HEALTHY" if excess>=0 else ("MARGIN_CALL" if ratio>Decimal("0.5") else "LIQUIDATION_ELIGIBLE")
        return {"equity":equity,"maintenance_requirement":maintenance,"margin_excess":excess,"margin_ratio":ratio,"health_state":state,"simulation":True}
    evaluate_transition=calculate


class LiquidationPlanner:
    @staticmethod
    def generate_plan(*, required_reduction, positions):
        required=_decimal(required_reduction,"required_reduction"); remaining=required; items=[]
        for position in sorted(positions,key=lambda x:(-x["margin_consumption"],str(x["instrument_id"]))):
            if remaining<=0: break
            if not position.get("active") or not position.get("fresh") or not position.get("market_open"): continue
            reduction=min(position["notional"],remaining); items.append({"instrument_id":position["instrument_id"],"estimated_notional":reduction,"reason":"MARGIN_CONSUMPTION","simulation":True}); remaining-=reduction
        return {"eligible":remaining<=0,"required_reduction":required,"proposed_positions":items,"uncovered":remaining,"simulation":True}
