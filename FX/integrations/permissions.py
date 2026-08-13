from django.conf import settings
from django.utils import timezone
from rest_framework import authentication, exceptions, permissions

from .models import Organization, OrganizationMembership, ServiceToken
from .crypto import token_digest


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
        org_id = request.headers.get("X-Organization-ID") or request.data.get("organization_id")
        if not org_id:
            return request.user.is_staff
        return OrganizationMembership.objects.filter(user=request.user, organization_id=org_id, role__in=["admin", "owner"]).exists()


def organization_for_request(request):
    if getattr(request, "service_token", None):
        return request.service_token.organization
    org_id = request.headers.get("X-Organization-ID") or request.data.get("organization_id")
    if org_id:
        return OrganizationMembership.objects.get(user=request.user, organization_id=org_id).organization
    membership = OrganizationMembership.objects.filter(user=request.user).select_related("organization").first()
    if membership:
        return membership.organization
    # Staging/demo users are assigned to the isolated Codestra staging tenant.
    # Production requires an explicit membership and never uses this fallback.
    if request.user.is_staff or getattr(request.user, "is_guest_demo", False) or getattr(settings, "PAPER_TRADING_ONLY", False):
        organization = Organization.objects.filter(name="Codestra staging").first()
        if not organization:
            organization = Organization.objects.create(name="Codestra staging")
        OrganizationMembership.objects.get_or_create(user=request.user, organization=organization, defaults={"role": "owner" if request.user.is_staff else "member"})
        return organization
    raise exceptions.PermissionDenied("organization context required")


def organization_for_user(user_id):
    """Resolve the default tenant for background notification/webhook work."""
    membership = OrganizationMembership.objects.filter(user_id=user_id).select_related("organization").first()
    if membership:
        return membership.organization
    user = __import__("users.models", fromlist=["User"]).User.objects.filter(pk=user_id).first()
    if user and getattr(user, "is_guest_demo", False):
        organization, _ = Organization.objects.get_or_create(name="Codestra staging")
        OrganizationMembership.objects.get_or_create(user_id=user_id, organization=organization, defaults={"role": "member"})
        return organization
    return None
