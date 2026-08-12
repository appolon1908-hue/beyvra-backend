from rest_framework.permissions import BasePermission

from .models import OperatorRole
from .services import tenant_for


class IsScopedOperator(BasePermission):
    allowed_roles = frozenset()

    def has_permission(self, request, view):
        if not request.user.is_authenticated or not request.user.is_staff:
            return False
        if not (
            request.user.is_mfa_enabled
            and request.user.two_factor_authentication_enabled
        ):
            return False
        tenant = request.headers.get(
            "X-Beyvra-Tenant", tenant_for(request.user)
        ).lower()
        return OperatorRole.objects.filter(
            user=request.user, tenant_id=tenant, role__in=self.allowed_roles
        ).exists()


class IsSupportOperator(IsScopedOperator):
    allowed_roles = frozenset(
        {"support_viewer", "support_agent", "support_manager", "platform_admin"}
    )


class IsSecurityManager(IsScopedOperator):
    allowed_roles = frozenset({"security_manager", "platform_admin"})


class IsSecurityOperator(IsScopedOperator):
    allowed_roles = frozenset(
        {"security_viewer", "security_analyst", "security_manager", "platform_admin"}
    )


class IsSecurityAnalyst(IsScopedOperator):
    allowed_roles = frozenset(
        {"security_analyst", "security_manager", "platform_admin"}
    )


class IsSupportAgent(IsScopedOperator):
    allowed_roles = frozenset({"support_agent", "support_manager", "platform_admin"})


class IsComplianceManager(IsScopedOperator):
    allowed_roles = frozenset({"compliance_manager", "platform_admin"})


class IsComplianceOperator(IsScopedOperator):
    allowed_roles = frozenset(
        {"compliance_viewer", "compliance_analyst", "compliance_manager", "platform_admin"}
    )


class IsFinancialOperator(IsScopedOperator):
    allowed_roles = frozenset(
        {"financial_viewer", "financial_operations", "financial_manager", "platform_admin"}
    )


class IsFinancialManager(IsScopedOperator):
    allowed_roles = frozenset({"financial_manager", "platform_admin"})


class IsOperationsManager(IsScopedOperator):
    allowed_roles = frozenset({"operations_manager", "platform_admin"})


class IsManagerOperator(IsScopedOperator):
    allowed_roles = frozenset(
        {
            "support_manager",
            "security_manager",
            "compliance_manager",
            "financial_manager",
            "operations_manager",
            "platform_admin",
        }
    )


class IsAnyOperator(IsScopedOperator):
    allowed_roles = frozenset(
        {
            "support_viewer",
            "support_agent",
            "support_manager",
            "security_viewer",
            "security_analyst",
            "security_manager",
            "compliance_viewer",
            "compliance_analyst",
            "compliance_manager",
            "financial_viewer",
            "financial_operations",
            "financial_manager",
            "operations_viewer",
            "operations_engineer",
            "operations_manager",
            "platform_admin",
        }
    )
