from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import ComplianceProfile, Restriction, TransactionScreening


class ComplianceRestrictionError(ValueError):
    code = "COMPLIANCE_RESTRICTION"


def check_wallet_permission(*, tenant, wallet, action):
    profile = ComplianceProfile.objects.filter(tenant=tenant).first()
    if profile is None or profile.status != "APPROVED":
        raise ComplianceRestrictionError("compliance profile is not approved")
    active = Restriction.objects.filter(tenant=tenant, active=True).filter(wallet__isnull=True) | Restriction.objects.filter(
        tenant=tenant, wallet=wallet, active=True
    )
    now = timezone.now()
    if active.filter(expires_at__isnull=True).exists() or active.filter(expires_at__gt=now).exists():
        raise ComplianceRestrictionError(f"wallet action is restricted: {action}")
    return True


@transaction.atomic
def screen_transaction(*, tenant, asset_network, direction, amount_atomic, destination=""):
    amount = Decimal(str(amount_atomic))
    if amount <= 0:
        raise ValueError("screening amount must be positive")
    return TransactionScreening.objects.create(
        tenant=tenant, asset_network=asset_network, direction=direction,
        amount_atomic=amount, destination=destination, status="PENDING",
    )


def approve_screening(screening_id, reason=""):
    screening = TransactionScreening.objects.get(pk=screening_id)
    if screening.status not in {"PENDING", "REVIEW"}:
        raise ValueError("screening is not reviewable")
    screening.status = "APPROVED"
    screening.decision_reason = reason[:255]
    screening.save(update_fields=["status", "decision_reason", "updated_at"])
    return screening


def reject_screening(screening_id, reason):
    screening = TransactionScreening.objects.get(pk=screening_id)
    if screening.status not in {"PENDING", "REVIEW"}:
        raise ValueError("screening is not reviewable")
    screening.status = "REJECTED"
    screening.decision_reason = reason[:255]
    screening.save(update_fields=["status", "decision_reason", "updated_at"])
    return screening
