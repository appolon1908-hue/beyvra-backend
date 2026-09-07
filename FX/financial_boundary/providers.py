from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from django.conf import settings

from apps.foundation.observability import record_live_effect


class ProviderDenied(PermissionError):
    code = "PROVIDER_OPERATION_DENIED"


class ProviderState(str, Enum):
    DISCOVERED = "DISCOVERED"
    CONFIGURED = "CONFIGURED"
    CREDENTIAL_PRESENT = "CREDENTIAL_PRESENT"
    TECHNICALLY_CERTIFIED = "TECHNICALLY_CERTIFIED"
    SECURITY_APPROVED = "SECURITY_APPROVED"
    COMPLIANCE_APPROVED = "COMPLIANCE_APPROVED"
    FINANCIAL_APPROVED = "FINANCIAL_APPROVED"
    STAGING_APPROVED = "STAGING_APPROVED"
    PRODUCTION_APPROVED = "PRODUCTION_APPROVED"
    DISABLED = "DISABLED"


class CustodyProvider(Protocol):
    def health(self): ...

    def capabilities(self): ...

    def create_deposit_destination(self, request): ...

    def get_deposit_status(self, reference): ...

    def validate_withdrawal(self, request): ...

    def submit_withdrawal(self, request): ...

    def get_withdrawal(self, reference): ...

    def cancel_withdrawal_if_supported(self, reference): ...


class PaymentProvider(Protocol):
    def health(self): ...

    def capabilities(self): ...

    def create_funding_intent(self, request): ...

    def get_funding_status(self, reference): ...

    def create_payout(self, request): ...

    def get_payout_status(self, reference): ...

    def cancel_payout_if_supported(self, reference): ...


@dataclass(frozen=True)
class ProviderAuthorization:
    provider_type: str = ""
    provider_enabled: bool = False
    environment_approved: bool = False
    operation_allowed: bool = False
    compliance_approved: bool = False
    financial_approved: bool = False
    feature_enabled: bool = False


def guard_outbound(authority: ProviderAuthorization):
    activation = {
        "CUSTODY": getattr(settings, "CUSTODY_PROVIDER_ACTIVATED", False),
        "PAYMENT": getattr(settings, "PAYMENT_PROVIDER_ACTIVATED", False),
    }.get(authority.provider_type, False)
    approvals = (
        authority.provider_enabled,
        authority.environment_approved,
        authority.operation_allowed,
        authority.compliance_approved,
        authority.financial_approved,
        authority.feature_enabled,
    )
    if (
        not getattr(settings, "REAL_MONEY_ENABLED", False)
        or not activation
        or not all(approvals)
    ):
        raise ProviderDenied("provider operation denied")
    effect = {
        "CUSTODY": "custody_provider",
        "PAYMENT": "payment_provider",
    }.get(authority.provider_type, "payment_provider")
    record_live_effect(effect, "attempt")
    return True


class DisabledProvider:
    def __getattr__(self, name):
        def denied(*args, **kwargs):
            raise ProviderDenied("provider disabled")

        return denied
