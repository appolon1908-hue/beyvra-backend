from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from .models import FxValuationRate


class FxValuationService:
    @staticmethod
    def _one_leg(rows, base, quote):
        direct = rows.filter(base_currency=base, quote_currency=quote).order_by("-rate_time").first()
        if direct:
            return direct.rate, [direct]
        inverse = rows.filter(base_currency=quote, quote_currency=base).order_by("-rate_time").first()
        if inverse and inverse.rate > 0:
            return Decimal("1") / inverse.rate, [inverse]
        raise ValueError("FX_RATE_UNAVAILABLE")

    @classmethod
    def resolve_rate(cls, base, quote, *, at=None):
        base, quote, at = base.upper(), quote.upper(), at or timezone.now()
        if base == quote:
            return Decimal("1"), [], "IDENTITY"
        rows = FxValuationRate.objects.filter(rate_time__lte=at, quality_state__in=("FRESH", "CORRECTED"))
        try:
            rate, refs = cls._one_leg(rows, base, quote)
            direct = refs[0].base_currency == base
            return rate, refs, "DIRECT" if direct else "INVERSE"
        except ValueError:
            pass
        for pivot in ("USD", "EUR"):
            if pivot in (base, quote):
                continue
            try:
                left, left_refs = cls._one_leg(rows, base, pivot)
                right, right_refs = cls._one_leg(rows, pivot, quote)
                return left * right, left_refs + right_refs, f"TRIANGULATED_{pivot}"
            except ValueError:
                continue
        raise ValueError("FX_RATE_UNAVAILABLE")

    @classmethod
    def convert(cls, amount, base, quote, *, at=None):
        rate, refs, chain = cls.resolve_rate(base, quote, at=at)
        return Decimal(amount) * rate, refs, chain
