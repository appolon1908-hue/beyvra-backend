import os

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def financial_database_isolation(_app_configs=None, **_kwargs):
    errors = []
    if set(settings.DATABASES) != {"default"}:
        errors.append(Error("Application backend must have exactly one non-financial database alias.", id="codestra.E001"))
    forbidden = ("FINANCIAL_DB_HOST", "FINANCIAL_DB_NAME", "FINANCIAL_DB_USER", "FINANCIAL_DB_PASSWORD", "FINANCIAL_DATABASE_URL")
    present = [name for name in forbidden if os.getenv(name)]
    if present:
        errors.append(Error("Financial PostgreSQL credentials are forbidden in the application process.", hint=",".join(present), id="codestra.E002"))
    safety_flags = (
        "REAL_WALLET_READ_ENABLED",
        "REAL_DEPOSITS_ENABLED",
        "REAL_WITHDRAWALS_ENABLED",
        "REAL_INTERNAL_TRANSFERS_ENABLED",
        "REAL_TRADING_ENABLED",
        "EXTERNAL_EXECUTION_ENABLED",
        "REAL_MONEY_ENABLED",
    )
    if any(getattr(settings, flag, False) for flag in safety_flags):
        errors.append(Error("P0 real-money and execution flags must remain disabled.", id="codestra.E003"))
    if getattr(settings, "SIMULATED_TRADING_REQUESTED", False) and getattr(settings, "DEPLOYMENT_ENV", "") not in {
        "local",
        "test",
        "staging",
    }:
        errors.append(
            Error(
                "Simulation trading is forbidden outside local, test, and staging environments.",
                id="codestra.E004",
            )
        )
    return errors
