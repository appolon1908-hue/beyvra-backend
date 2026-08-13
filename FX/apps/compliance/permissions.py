from rest_framework.permissions import BasePermission

ROLE_ORDER = {"compliance_viewer": 1, "compliance_analyst": 2, "compliance_manager": 3}
class ComplianceRolePermission(BasePermission):
    minimum_role = "compliance_viewer"
    def has_permission(self, request, view):
        memberships = getattr(request.user, "organizationmembership_set", None)
        return bool(request.user.is_authenticated and memberships and any(ROLE_ORDER.get(x.role, 0) >= ROLE_ORDER[self.minimum_role] for x in memberships.all()))

class IsComplianceViewer(ComplianceRolePermission): minimum_role = "compliance_viewer"
class IsComplianceAnalyst(ComplianceRolePermission): minimum_role = "compliance_analyst"
class IsComplianceManager(ComplianceRolePermission): minimum_role = "compliance_manager"

def authorized_organization_ids(user, minimum_role):
    threshold = ROLE_ORDER[minimum_role]
    return [membership.organization_id for membership in user.organizationmembership_set.all() if ROLE_ORDER.get(membership.role, 0) >= threshold]
