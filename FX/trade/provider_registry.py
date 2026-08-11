"""Approval and readiness records for market/news/calendar providers."""
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ProviderApproval:
    provider_code: str
    service_type: str
    approved_environment: str
    supported_symbols: frozenset[str]
    supported_timeframes: frozenset[str]
    delay_status: str
    redistribution_rights: bool
    display_rights: bool
    storage_rights: bool
    credential_reference: str | None
    approval_reference: str | None
    expires_at: str | None

    @property
    def approved(self):
        return bool(self.approval_reference and self.approved_environment == "staging")


def provider_readiness(approval: ProviderApproval) -> dict:
    expired = False
    if approval.expires_at:
        expired = datetime.fromisoformat(approval.expires_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    return {
        "provider": approval.provider_code,
        "status": "APPROVED" if approval.approved and not expired else "BLOCKED",
        "credential_status": "CONFIGURED" if approval.credential_reference else "MISSING",
        "license_status": "APPROVED" if approval.display_rights and approval.storage_rights else "REVIEW_REQUIRED",
    }
