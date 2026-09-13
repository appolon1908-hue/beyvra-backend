"""Canonical tenant and economic-account identity for trading operations."""

from dataclasses import dataclass
import uuid

from rest_framework import exceptions

from integrations.models import Organization, OrganizationMembership
from integrations.permissions import tenant_context_for_request


@dataclass(frozen=True)
class TradingContext:
    organization_id: uuid.UUID
    tenant_ref: str
    subject_ref: str
    account_ref: str
    user_id: int
    user: object
    source: str

    @classmethod
    def from_request(cls, request):
        resolved = tenant_context_for_request(request)
        return cls._build(request.user, resolved.organization, resolved.source)

    @classmethod
    def for_user(cls, user, organization_id=None):
        memberships = OrganizationMembership.objects.filter(
            user=user,
            is_active=True,
            organization__is_active=True,
        ).select_related("organization").order_by("organization_id")
        if organization_id is not None:
            try:
                organization_id = uuid.UUID(str(organization_id))
            except (TypeError, ValueError, AttributeError):
                raise ValueError("INVALID_ORGANIZATION")
            membership = memberships.filter(organization_id=organization_id).first()
            if membership is None:
                raise ValueError("ORGANIZATION_NOT_AUTHORIZED")
            return cls._build(user, membership.organization, "explicit-service-context")
        available = list(memberships[:2])
        if len(available) != 1:
            raise ValueError("TENANT_SELECTION_REQUIRED" if available else "ORGANIZATION_REQUIRED")
        return cls._build(user, available[0].organization, "single-membership")

    @classmethod
    def _build(cls, user, organization: Organization, source: str):
        tenant_ref = str(organization.id)
        subject_ref = str(user.pk)
        return cls(
            organization_id=organization.id,
            tenant_ref=tenant_ref,
            subject_ref=subject_ref,
            account_ref=f"paper:{tenant_ref}:{subject_ref}",
            user_id=user.pk,
            user=user,
            source=source,
        )


def require_trading_context(value):
    if isinstance(value, TradingContext):
        return value
    return TradingContext.for_user(value)


def context_error_code(error):
    if isinstance(error, exceptions.ValidationError) and isinstance(error.detail, dict):
        return str(error.detail.get("code", "TENANT_SELECTION_REQUIRED"))
    if isinstance(error, exceptions.PermissionDenied):
        return "ORGANIZATION_NOT_AUTHORIZED"
    return str(error)
