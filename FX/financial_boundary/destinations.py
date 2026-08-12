"""Opaque, tenant-safe withdrawal destination metadata and syntax validation."""

from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
import re
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .contracts import canonical_asset
from .models import Destination


BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class DestinationValidationError(ValueError):
    code = "INVALID_DESTINATION"


class DestinationAccessDenied(PermissionError):
    code = "DESTINATION_NOT_FOUND"


def validate_crypto_destination(*, asset: str, network: str, value: str) -> str:
    asset = canonical_asset(asset)
    if not isinstance(network, str) or not re.fullmatch(r"[A-Z][A-Z0-9_-]{1,31}", network):
        raise DestinationValidationError("invalid network")
    if not isinstance(value, str) or value != value.strip():
        raise DestinationValidationError("invalid address")
    valid = False
    if network == "ETHEREUM":
        valid = asset == "ETH" and bool(re.fullmatch(r"0x[0-9a-fA-F]{40}", value))
    elif network == "BITCOIN":
        valid = asset == "BTC" and bool(
            re.fullmatch(r"(?:bc1[ac-hj-np-z02-9]{11,71}|[13][%s]{25,61})" % BASE58, value)
        )
    elif network == "BITCOIN_TESTNET":
        valid = asset == "BTC" and bool(
            re.fullmatch(r"(?:tb1[ac-hj-np-z02-9]{11,71}|[mn2][%s]{25,61})" % BASE58, value)
        )
    elif network == "SOLANA":
        valid = asset == "SOL" and bool(re.fullmatch(rf"[{BASE58}]{{32,44}}", value))
    if not valid:
        raise DestinationValidationError("address syntax does not match network")
    return value


def validate_fiat_destination(*, asset: str, network: str, value: str) -> str:
    canonical_asset(asset)
    if network != "PROVIDER_REFERENCE":
        raise DestinationValidationError("fiat destination must be an opaque provider reference")
    if not isinstance(value, str) or not re.fullmatch(
        r"provider:[a-z0-9_-]{2,32}:customer:[A-Za-z0-9._-]{6,64}", value
    ):
        raise DestinationValidationError("invalid provider customer reference")
    return value


def _fingerprint(value: str) -> str:
    key = getattr(settings, "DESTINATION_FINGERPRINT_KEY", "")
    if not isinstance(key, str) or len(key.encode("utf-8")) < 32:
        raise RuntimeError("destination fingerprint key is unavailable")
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _masked(value: str, destination_type: str) -> str:
    if destination_type == Destination.Type.CRYPTO:
        return f"{value[:6]}…{value[-4:]}"
    provider = value.split(":", 2)[1]
    return f"provider:{provider}:customer:…{value[-4:]}"


@transaction.atomic
def create_destination(*, tenant_ref, account_ref, owner_ref: int, destination_type: str,
                       asset: str, network: str, value: str, beneficiary_ref=None,
                       cooldown=timedelta(hours=24)) -> Destination:
    if destination_type == Destination.Type.CRYPTO:
        validated = validate_crypto_destination(asset=asset, network=network, value=value)
    elif destination_type == Destination.Type.FIAT:
        validated = validate_fiat_destination(asset=asset, network=network, value=value)
    else:
        raise DestinationValidationError("unsupported destination type")
    if not isinstance(owner_ref, int) or isinstance(owner_ref, bool) or owner_ref < 1:
        raise DestinationValidationError("invalid owner")
    if not isinstance(cooldown, timedelta) or cooldown < timedelta(0):
        raise DestinationValidationError("invalid cooldown")
    return Destination.objects.create(
        tenant_ref=uuid.UUID(str(tenant_ref)), account_ref=uuid.UUID(str(account_ref)),
        owner_ref=owner_ref, type=destination_type, asset=canonical_asset(asset),
        network=network, masked_display=_masked(validated, destination_type),
        destination_fingerprint=_fingerprint(validated),
        beneficiary_ref=uuid.UUID(str(beneficiary_ref)) if beneficiary_ref else None,
        cooldown_until=timezone.now() + cooldown,
    )


def get_destination_for_withdrawal(*, destination_id, tenant_ref, account_ref, owner_ref: int,
                                   now=None) -> Destination:
    destination = Destination.objects.filter(
        destination_id=destination_id, tenant_ref=tenant_ref,
        account_ref=account_ref, owner_ref=owner_ref,
    ).first()
    if destination is None:
        raise DestinationAccessDenied("destination not found")
    if destination.status != Destination.Status.VERIFIED or destination.verified_at is None:
        raise DestinationValidationError("DESTINATION_NOT_VERIFIED")
    if destination.cooldown_until and destination.cooldown_until > (now or timezone.now()):
        raise DestinationValidationError("DESTINATION_COOLDOWN")
    return destination


@transaction.atomic
def revoke_destination(*, destination_id, tenant_ref, account_ref, owner_ref: int) -> Destination:
    destination = Destination.objects.select_for_update().filter(
        destination_id=destination_id, tenant_ref=tenant_ref,
        account_ref=account_ref, owner_ref=owner_ref,
    ).first()
    if destination is None:
        raise DestinationAccessDenied("destination not found")
    destination.status = Destination.Status.REVOKED
    destination.save(update_fields=["status"])
    return destination
