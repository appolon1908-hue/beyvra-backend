from rest_framework.permissions import BasePermission, SAFE_METHODS

from integrations.models import OrganizationMembership


OPERATOR_ROLES = {"institutional_viewer", "institutional_operations", "institutional_risk_analyst", "institutional_manager", "custody_operations", "clearing_operations"}
MUTATION_ROLES = OPERATOR_ROLES - {"institutional_viewer", "institutional_risk_analyst"}
MANAGER_ROLES = {"institutional_manager"}


def active_memberships(user):
    return OrganizationMembership.objects.filter(
        user=user, is_active=True, organization__is_active=True,
    )


class IsInstitutionMember(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        memberships = active_memberships(request.user)
        organization_id = getattr(request, "organization_id", None)
        if organization_id:
            memberships = memberships.filter(organization_id=organization_id)
        return memberships.exists()


class IsInstitutionalOperator(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        roles = OPERATOR_ROLES if request.method in SAFE_METHODS else MUTATION_ROLES
        return request.user.is_superuser or active_memberships(request.user).filter(role__in=roles).exists()


class IsInstitutionalManager(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or active_memberships(request.user).filter(role__in=MANAGER_ROLES).exists()
