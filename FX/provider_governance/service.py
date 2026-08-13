from dataclasses import dataclass
from pathlib import Path
import errno
import hashlib
import json
import os
import re
import stat
import uuid

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import APIException

from .models import ProviderApproval, ProviderDefinition, ProviderGovernanceAudit


class ProviderNotAvailable(APIException):
    status_code = 503
    default_detail = "PROVIDER_NOT_AVAILABLE"
    default_code = "provider_not_available"


@dataclass(frozen=True)
class ResolvedProvider:
    provider_id: str
    provider_type: str
    approval_id: int
    approval_version: int
    credential_path: str | None


def approval_payload_hash(approval):
    payload = {
        "provider_id": approval.provider.provider_id,
        "provider_type": approval.provider_type,
        "environment": approval.environment,
        "version": approval.version,
        "status": approval.status,
        "approval_reference": approval.approval_reference,
        "approved_by_principal_id": approval.approved_by_principal_id,
        "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
        "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
        "license_id": approval.license_id,
        "credential_policy": approval.credential_policy,
        "credential_reference": approval.credential_reference,
        "allowed_products": approval.allowed_products,
        "allowed_symbols": approval.allowed_symbols,
        "allowed_regions": approval.allowed_regions,
        "supersedes_approval_id": approval.supersedes_approval_id,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _audit(*, provider, approval, decision, reason, provider_id, provider_type, product, symbol, region, request_id, correlation_id, caller_service):
    credential_ref = approval.credential_reference if approval else ""
    ProviderGovernanceAudit.objects.create(
        audit_event_id=uuid.uuid4(), provider=provider,
        provider_id_evidence=provider_id, provider_type=provider_type, environment="STAGING",
        approval=approval, approval_version=approval.version if approval else None,
        license=approval.license if approval else None, decision=decision, reason_code=reason,
        requested_product=product, requested_symbol=symbol, requested_region=region,
        credential_reference_id=credential_ref or "",
        credential_reference_hash=hashlib.sha256((credential_ref or "").encode()).hexdigest() if credential_ref else "",
        request_id=request_id or "", correlation_id=correlation_id or "", caller_service=caller_service,
    )


def _deny(context, reason):
    _audit(**context, decision="DENIED", reason=reason)
    raise ProviderNotAvailable("PROVIDER_NOT_AVAILABLE")


def _has_acl(path):
    try:
        return bool(os.getxattr(path, "system.posix_acl_access", follow_symlinks=False))
    except OSError as exc:
        if exc.errno in (errno.ENODATA, errno.ENOTSUP, errno.EOPNOTSUPP):
            return False
        return True


def _credential_path(reference):
    if not reference or not re.search(r"(^|/)v[1-9][0-9]*(/|$)", reference):
        return None
    root = Path(settings.PROVIDER_CREDENTIAL_ROOT).absolute()
    candidate = root / reference
    allowed_uids = {int(uid) for uid in str(getattr(settings, "PROVIDER_CREDENTIAL_ALLOWED_UIDS", "0")).split(",") if uid.strip()}
    current = root
    try:
        root_stat = os.lstat(root)
        if stat.S_ISLNK(root_stat.st_mode): return None
        for part in Path(reference).parts:
            if part in ("", ".", ".."):
                return None
            current = current / part
            item_stat = os.lstat(current)
            if stat.S_ISLNK(item_stat.st_mode) or item_stat.st_uid not in allowed_uids or _has_acl(current):
                return None
            if current != candidate and item_stat.st_mode & 0o022:
                return None
        file_stat = os.lstat(candidate)
    except OSError:
        return None
    if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_mode & 0o077 or not os.access(candidate, os.R_OK):
        return None
    return str(candidate)


def resolve_provider(*, provider_id, provider_type, product, symbol, region, request_id="", correlation_id="", caller_service="unknown"):
    provider = ProviderDefinition.objects.filter(provider_id=provider_id).first()
    context = dict(provider=provider, approval=None, provider_id=provider_id, provider_type=provider_type,
                   product=product, symbol=symbol, region=region, request_id=request_id,
                   correlation_id=correlation_id, caller_service=caller_service)
    if provider is None: _deny(context, "PROVIDER_RECORD_MISSING")
    if provider.provider_type != provider_type: _deny(context, "PROVIDER_TYPE_MISMATCH")
    if not provider.enabled: _deny(context, "PROVIDER_DISABLED")
    if provider.environment != "STAGING": _deny(context, "ENVIRONMENT_NOT_ALLOWED")
    if not provider.license_verified: _deny(context, "LICENSE_NOT_VERIFIED")
    if not provider.security_approved: _deny(context, "SECURITY_NOT_APPROVED")
    if not provider.compliance_approved: _deny(context, "COMPLIANCE_NOT_APPROVED")
    if not provider.staging_approved: _deny(context, "STAGING_NOT_APPROVED")
    approval = ProviderApproval.objects.filter(provider=provider, environment="STAGING", status="APPROVED", replacement__isnull=True).select_related("license").first()
    context["approval"] = approval
    if approval is None: _deny(context, "APPROVAL_MISSING")
    now = timezone.now()
    if approval.provider_type != provider.provider_type or not approval.approved_at: _deny(context, "APPROVAL_INVALID")
    if approval.expires_at and approval.expires_at <= now: _deny(context, "APPROVAL_EXPIRED")
    if approval.approval_payload_hash != approval_payload_hash(approval): _deny(context, "APPROVAL_HASH_INVALID")
    license_record = approval.license
    if license_record is None or license_record.provider_id != provider.id or license_record.environment != "STAGING" or license_record.status != "APPROVED":
        _deny(context, "LICENSE_INVALID")
    if license_record.expires_at and license_record.expires_at <= now: _deny(context, "LICENSE_EXPIRED")
    for value, allowed, reason in ((product, approval.allowed_products, "PRODUCT_NOT_ALLOWED"), (symbol, approval.allowed_symbols, "SYMBOL_NOT_ALLOWED"), (region, approval.allowed_regions, "REGION_NOT_ALLOWED")):
        if "*" not in allowed and value not in allowed: _deny(context, reason)
    if approval.credential_policy == "NONE":
        credential_path = None
    elif approval.credential_policy == "REQUIRED":
        credential_path = _credential_path(approval.credential_reference)
        if credential_path is None: _deny(context, "CREDENTIAL_UNRESOLVABLE")
    else:
        _deny(context, "CREDENTIAL_POLICY_INVALID")
    _audit(**context, decision="ALLOWED", reason="GOVERNANCE_APPROVED")
    return ResolvedProvider(provider.provider_id, provider.provider_type, approval.id, approval.version, credential_path)
