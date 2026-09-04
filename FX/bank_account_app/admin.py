from django.contrib import admin
from .models import BankAccount, WithdrawalRequest

# Register your models here.


class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'bank_name', 'masked_account', 'account_holder_name',
                    'last_name', 'country', 'is_active')
    search_fields = ('user__email', 'bank_name', 'account_holder_name',
                     'last_name', 'country')
    readonly_fields = tuple(
        field.name for field in BankAccount._meta.fields
        if field.name not in {'id'}
    )

    @admin.display(description='Account')
    def masked_account(self, obj):
        return f"****{obj.account_number_last_four}" if obj.account_number_last_four else ""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'bank_account', 'amount', 'status',
                    'request_date', 'currency', 'description')
    search_fields = ('user', 'bank_account', 'amount', 'status',
                     'approved_by', 'request_date', 'currency', 'description')
    list_filter = ('status',)


admin.site.register(BankAccount, BankAccountAdmin)
admin.site.register(WithdrawalRequest, WithdrawalRequestAdmin)
