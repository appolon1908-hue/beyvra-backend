from django.contrib import admin

from .models import ProviderApproval, ProviderDefinition, ProviderGovernanceAudit, ProviderLicense


admin.site.register(ProviderDefinition)
admin.site.register(ProviderApproval)
admin.site.register(ProviderLicense)


@admin.register(ProviderGovernanceAudit)
class ProviderGovernanceAuditAdmin(admin.ModelAdmin):
    list_display = ("provider", "decision", "reason_code", "occurred_at")
    readonly_fields = ("provider", "decision", "reason_code", "occurred_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
