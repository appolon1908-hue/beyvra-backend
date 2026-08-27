from dataclasses import dataclass
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import authentication, exceptions, permissions

from .models import Organization, OrganizationMembership, ServiceToken
from .crypto import token_digest


STAGING_TENANT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "staging.beyvra.com")


@dataclass(frozen=True)
class TenantContext:
    organization: Organization
    role: str
    source: str


class ScopedBearerAuthentication(authentication.BaseAuthentication):
    """Bearer service tokens are stored only as SHA-256 hashes."""
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.lower().startswith("bearer "):
            return None
        raw = header.split(" ", 1)[1].strip()
        token = ServiceToken.objects.select_related("organization").filter(
            token_hash=token_digest(raw), is_active=True, revoked_at__isnull=True
        ).first()
        if not token or (token.expires_at and token.expires_at <= timezone.now()):
            raise exceptions.AuthenticationFailed("Invalid service token")
        request.service_token = token
        ServiceToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        return (token.organization, token)

    def authenticate_header(self, request):
        return "Bearer"


class HasScope(permissions.BasePermission):
    required_scope = None

    def has_permission(self, request, view):
        if getattr(request, "service_token", None):
            return getattr(view, "required_scope", self.required_scope) in request.service_token.scopes
        if not request.user or not request.user.is_authenticated:
            raise exceptions.NotAuthenticated("Bearer authentication is required")
        org_id = request.headers.get("X-Organization-ID")
        if not org_id:
            return request.user.is_staff
        return OrganizationMembership.objects.filter(
            user=request.user,
            organization_id=org_id,
            organization__is_active=True,
            is_active=True,
            role__in=["admin", "owner"],
        ).exists()


def _staging_context(user):
    organization, _ = Organization.objects.get_or_create(
        pk=STAGING_TENANT_ID,
        defaults={"name": "Beyvra staging", "is_active": True},
    )
    if not organization.is_active:
        raise exceptions.PermissionDenied("organization is inactive")
    membership, _ = OrganizationMembership.objects.get_or_create(
        user=user,
        organization=organization,
        defaults={"role": "owner" if user.is_staff else "member", "is_active": True},
    )
    if not membership.is_active:
        raise exceptions.PermissionDenied("organization membership is inactive")
    return TenantContext(organization=organization, role=membership.role, source="staging-fallback")


def tenant_context_for_request(request):
    """Resolve exactly one active tenant without trusting request-body tenancy."""
    if getattr(request, "service_token", None):
        organization = request.service_token.organization
        if not organization.is_active:
            raise exceptions.PermissionDenied("organization is inactive")
        return TenantContext(organization=organization, role="service", source="service-token")

    org_id = request.headers.get("X-Organization-ID")
    memberships = OrganizationMembership.objects.filter(
        user=request.user,
        is_active=True,
        organization__is_active=True,
    ).select_related("organization").order_by("organization_id")

    if org_id:
        try:
            normalized_org_id = uuid.UUID(str(org_id))
        except (ValueError, TypeError, AttributeError):
            raise exceptions.PermissionDenied("invalid organization context")
        try:
            membership = memberships.get(organization_id=normalized_org_id)
        except (OrganizationMembership.DoesNotExist, DjangoValidationError):
            raise exceptions.PermissionDenied("organization context is not authorized")
        return TenantContext(
            organization=membership.organization,
            role=membership.role,
            source="request-header",
        )

    available = list(memberships[:2])
    if len(available) == 1:
        membership = available[0]
        return TenantContext(
            organization=membership.organization,
            role=membership.role,
            source="single-membership",
        )
    if len(available) > 1:
        raise exceptions.ValidationError({
            "code": "TENANT_SELECTION_REQUIRED",
            "detail": "X-Organization-ID is required for accounts with multiple active tenants.",
        })
    if request.user.is_staff or getattr(request.user, "is_guest_demo", False) or getattr(settings, "PAPER_TRADING_ONLY", False):
        return _staging_context(request.user)
    raise exceptions.PermissionDenied("organization context required")


def organization_for_request(request):
    return tenant_context_for_request(request).organization


def organization_for_user(user_id):
    """Resolve the default tenant for background notification/webhook work."""
    memberships = list(OrganizationMembership.objects.filter(
        user_id=user_id,
        is_active=True,
        organization__is_active=True,
    ).select_related("organization").order_by("organization_id")[:2])
    if len(memberships) == 1:
        return memberships[0].organization
    if len(memberships) > 1:
        return None
    user = __import__("users.models", fromlist=["User"]).User.objects.filter(pk=user_id).first()
    if user and getattr(user, "is_guest_demo", False):
        return _staging_context(user).organization
    return None
