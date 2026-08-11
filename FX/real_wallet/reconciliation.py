from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import AssetBalance, ReconciliationItem, ReconciliationRun


@transaction.atomic
def run_balance_reconciliation(*, tenant, external_balances):
    """Compare the local projection with a provider snapshot without mutating money."""
    run = ReconciliationRun.objects.create(
        tenant=tenant, scope="BALANCES", status="RUNNING", started_at=timezone.now()
    )
    local = {
        (str(balance.asset_network.asset_id), str(balance.asset_network.network_id)): balance.posted_atomic
        for balance in AssetBalance.objects.filter(wallet__tenant=tenant).select_related("asset_network")
    }
    keys = set(local) | set(external_balances)
    matched = exceptions = 0
    for key in sorted(keys):
        internal = Decimal(str(local.get(key, 0)))
        external = Decimal(str(external_balances.get(key, 0)))
        result = "MATCHED" if internal == external else "AMOUNT_MISMATCH"
        if result == "MATCHED":
            matched += 1
        else:
            exceptions += 1
        ReconciliationItem.objects.create(
            run=run, resource_type="asset_network", result=result,
            internal_amount_atomic=internal, external_amount_atomic=external,
            reason="" if result == "MATCHED" else "local and external balances differ",
        )
    run.status = "COMPLETED" if exceptions == 0 else "EXCEPTIONS"
    run.completed_at = timezone.now()
    run.summary = {"matched": matched, "exceptions": exceptions}
    run.save(update_fields=["status", "completed_at", "summary", "updated_at"])
    return run
