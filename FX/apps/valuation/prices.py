from datetime import timedelta

from django.utils import timezone

from .models import ValuationPrice


class ValuationPriceService:
    INTRADAY = ("MID", "LAST", "BID", "ASK")
    END_OF_DAY = ("OFFICIAL_CLOSE", "SETTLEMENT_PRICE", "NAV_PRICE")

    @classmethod
    def resolve(cls, instrument_id, *, purpose="INTRADAY", at=None, max_age=timedelta(minutes=5)):
        at = at or timezone.now()
        precedence = cls.END_OF_DAY if purpose == "END_OF_DAY_NAV" else cls.INTRADAY
        rows = ValuationPrice.objects.filter(instrument_id=instrument_id, valuation_time__lte=at, quality_state__in=("FRESH", "CORRECTED"))
        for price_type in precedence:
            row = rows.filter(price_type=price_type).order_by("-valuation_time").first()
            if row:
                cls.validate_freshness(row, at=at, max_age=max_age)
                return row
        raise ValueError("VALUATION_PRICE_UNAVAILABLE")

    @classmethod
    def resolve_historical(cls, instrument_id, *, at, purpose="END_OF_DAY_NAV", max_age=timedelta(days=4)):
        return cls.resolve(instrument_id, purpose=purpose, at=at, max_age=max_age)

    @staticmethod
    def validate_freshness(price, *, at=None, max_age=timedelta(minutes=5)):
        if price.quality_state not in ("FRESH", "CORRECTED") or (at or timezone.now()) - price.valuation_time > max_age:
            raise ValueError("VALUATION_PRICE_STALE")
        if price.price <= 0:
            raise ValueError("VALUATION_PRICE_INVALID")
        return True

