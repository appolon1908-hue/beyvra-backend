from dataclasses import dataclass
from pathlib import Path
import os
import stat

from django.conf import settings
from django.utils import timezone

from .models import ProviderApproval, ProviderDefinition, ProviderGovernanceAudit, ProviderLicense


class ProviderNotAvailable(Exception):
    pass


@dataclass(frozen=True)
class ResolvedProvider:
    provider_id: str
    provider_type: str
    credential_path: str


def _deny(provider, reason):
    ProviderGovernanceAudit.objects.create(provider=provider, decision="DENIED", reason_code=reason)
    raise ProviderNotAvailable("PROVIDER_NOT_AVAILABLE")


def _credential_path(reference):
    root = Path(settings.PROVIDER_CREDENTIAL_ROOT).resolve()
    candidate = (root / reference).resolve()
    if root not in candidate.parents:
        return None
    try:
        mode = candidate.stat().st_mode
    except OSError:
        return None
    if not stat.S_ISREG(mode) or mode & 0o077 or not os.access(candidate, os.R_OK):
        return None
    return str(candidate)


def resolve_provider(*, provider_id, provider_type, product, symbol, region):
    now = timezone.now()
    try:
        provider = ProviderDefinition.objects.get(provider_id=provider_id, provider_type=provider_type)
    except ProviderDefinition.DoesNotExist:
        _deny(None, "PROVIDER_RECORD_MISSING")
    if not provider.enabled:
        _deny(provider, "PROVIDER_DISABLED")
    approval = ProviderApproval.objects.filter(provider=provider, environment="STAGING").order_by("-created_at").first()
    if approval is None:
        _deny(provider, "APPROVAL_MISSING")
    if approval.status != "APPROVED" or approval.provider_type != provider.provider_type:
        _deny(provider, "APPROVAL_INVALID")
    if not approval.approved_at or (approval.expires_at and approval.expires_at <= now):
        _deny(provider, "APPROVAL_EXPIRED")
    license_record = ProviderLicense.objects.filter(
        provider=provider,
        environment="STAGING",
        license_reference=approval.license_reference,
    ).first()
    if license_record is None or license_record.status != "APPROVED":
        _deny(provider, "LICENSE_INVALID")
    if license_record.expires_at and license_record.expires_at <= now:
        _deny(provider, "LICENSE_EXPIRED")
    for value, allowed, reason in (
        (product, approval.allowed_products, "PRODUCT_NOT_ALLOWED"),
        (symbol, approval.allowed_symbols, "SYMBOL_NOT_ALLOWED"),
        (region, approval.allowed_regions, "REGION_NOT_ALLOWED"),
    ):
        if "*" not in allowed and value not in allowed:
            _deny(provider, reason)
    credential_path = _credential_path(approval.credential_reference)
    if credential_path is None:
        _deny(provider, "CREDENTIAL_UNRESOLVABLE")
    ProviderGovernanceAudit.objects.create(provider=provider, decision="ALLOWED", reason_code="GOVERNANCE_APPROVED")
    return ResolvedProvider(provider.provider_id, provider.provider_type, credential_path)
