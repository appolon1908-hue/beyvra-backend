from django.contrib import admin

from .models import ProviderApproval, ProviderDefinition, ProviderGovernanceAudit, ProviderLicense


admin.site.register(ProviderDefinition)
admin.site.register(ProviderApproval)
admin.site.register(ProviderLicense)


@admin.register(ProviderGovernanceAudit)
class ProviderGovernanceAuditAdmin(admin.ModelAdmin):
    list_display = ("audit_event_id", "provider_id_evidence", "decision", "reason_code", "resolved_at")
    readonly_fields = tuple(field.name for field in ProviderGovernanceAudit._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
