from decimal import Decimal


def error_budget(target, good, bad):
    total=good+bad; allowed=Decimal(total)*(Decimal("1")-Decimal(target)); observed=Decimal(bad)
    remaining=max(Decimal("0"),allowed-observed)
    return {"allowed_bad_events":str(allowed),"observed_bad_events":str(observed),"remaining_budget":str(remaining),"burn_rate":str(observed/allowed if allowed else (Decimal("0") if not observed else Decimal("Infinity")))}
