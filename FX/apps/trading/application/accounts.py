"""Account identity operations shared by internal PAPER projections."""

from django.db import transaction

from apps.trading.models import SimulatedAccount, TradingAccount


@transaction.atomic
def ensure_paper_identity(projection):
    # Settlement already locks the projection before serializing identity.
    # Preserve that order while keeping account restrictions stable during an
    # enclosing order transaction.
    SimulatedAccount.objects.select_for_update().only("id").get(pk=projection.pk)
    account, _ = TradingAccount.objects.select_for_update().get_or_create(
        paper_projection=projection,
        defaults={
            "id": projection.id,
            "tenant_ref": projection.tenant_ref,
            "subject_ref": projection.subject_ref,
            "account_ref": projection.account_ref,
            "execution_mode": TradingAccount.ExecutionMode.PAPER,
            "base_currency": projection.quote_currency,
            "status": projection.status,
            "trading_enabled": projection.status == TradingAccount.Status.ACTIVE,
        },
    )
    if (
        account.tenant_ref != projection.tenant_ref
        or account.subject_ref != projection.subject_ref
        or account.account_ref != projection.account_ref
        or account.base_currency != projection.quote_currency
        or account.execution_mode != TradingAccount.ExecutionMode.PAPER
    ):
        raise ValueError("ACCOUNT_PROJECTION_MISMATCH")
    return account


def serialize_trading_account(account):
    return {
        "account_id": str(account.id),
        "execution_mode": account.execution_mode,
        "base_currency": account.base_currency,
        "status": account.status,
        "trading_enabled": account.trading_enabled,
        "funding_enabled": account.funding_enabled,
        "withdrawals_enabled": account.withdrawals_enabled,
    }
