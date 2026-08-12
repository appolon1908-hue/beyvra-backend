from rest_framework.permissions import BasePermission

from integrations.models import OrganizationMembership


OPERATOR_ROLES = {"institutional_viewer", "institutional_operations", "institutional_risk_analyst", "institutional_manager", "custody_operations", "clearing_operations"}
MANAGER_ROLES = {"institutional_manager"}


class IsInstitutionMember(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and OrganizationMembership.objects.filter(user=request.user, organization_id=request.organization_id).exists()) if getattr(request, "organization_id", None) else bool(request.user and request.user.is_authenticated and OrganizationMembership.objects.filter(user=request.user).exists())


class IsInstitutionalOperator(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or OrganizationMembership.objects.filter(user=request.user, role__in=OPERATOR_ROLES).exists()


class IsInstitutionalManager(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_superuser or OrganizationMembership.objects.filter(user=request.user, role__in=MANAGER_ROLES).exists()))
