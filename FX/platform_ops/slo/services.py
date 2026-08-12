from django.db.models import Sum
from .calculators import error_budget
from .models import SloDefinition


class ErrorBudgetService:
    @staticmethod
    def calculate(slo):
        totals=slo.sli.observations.aggregate(good=Sum("good_events"),bad=Sum("bad_events"))
        return {"slo":slo.code,**error_budget(slo.target,totals["good"] or 0,totals["bad"] or 0)}

    @classmethod
    def all(cls): return [cls.calculate(s) for s in SloDefinition.objects.filter(status="ACTIVE").select_related("sli")]
