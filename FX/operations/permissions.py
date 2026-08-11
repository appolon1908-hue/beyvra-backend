from rest_framework.permissions import BasePermission

from .models import OperatorRole
from .services import tenant_for


class IsScopedOperator(BasePermission):
    allowed_roles = frozenset()

    def has_permission(self, request, view):
        if not request.user.is_authenticated or not request.user.is_staff:
            return False
        tenant = request.headers.get("X-Beyvra-Tenant", tenant_for(request.user)).lower()
        return OperatorRole.objects.filter(user=request.user, tenant_id=tenant, role__in=self.allowed_roles).exists()


class IsSupportOperator(IsScopedOperator):
    allowed_roles = frozenset({"support_viewer", "support_agent", "support_manager", "platform_admin"})


class IsSecurityManager(IsScopedOperator):
    allowed_roles = frozenset({"security_manager", "platform_admin"})
