from decimal import Decimal
from .models import CapacityProfile

class CapacityAuthority:
    DEFAULT_SAFETY_FACTOR=Decimal("0.70")
    @classmethod
    def certify(cls,*,tested_limit,**values):
        tested=Decimal(str(tested_limit)); factor=Decimal(str(values.pop("safety_factor",cls.DEFAULT_SAFETY_FACTOR)))
        if not values.get("test_sha") or not values.get("evidence_ref"): raise ValueError("CAPACITY_EVIDENCE_REQUIRED")
        return CapacityProfile.objects.create(tested_limit=tested,safe_operating_limit=tested*factor,safety_factor=factor,**values)
