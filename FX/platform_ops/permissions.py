from integrations.models import OrganizationMembership
from rest_framework.permissions import BasePermission


SRE_ROLES = {"sre_viewer", "sre_operator", "sre_manager", "release_manager", "incident_commander", "security_operator"}


class IsSreViewer(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated: return False
        return request.user.is_superuser or OrganizationMembership.objects.filter(user=request.user, role__in=SRE_ROLES).exists()


class HasSreRole(BasePermission):
    roles = set()
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated: return False
        return request.user.is_superuser or OrganizationMembership.objects.filter(user=request.user, role__in=self.roles).exists()


class IsSreOperator(HasSreRole): roles = {"sre_operator", "sre_manager", "incident_commander"}
class IsSreManager(HasSreRole): roles = {"sre_manager"}
class IsReleaseManager(HasSreRole): roles = {"release_manager", "sre_manager"}
class IsIncidentCommander(HasSreRole): roles = {"incident_commander", "sre_manager"}
class IsSecurityOperator(HasSreRole): roles = {"security_operator", "sre_manager"}
