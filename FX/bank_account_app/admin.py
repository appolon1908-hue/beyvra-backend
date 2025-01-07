from django.contrib import admin
from .models import BankAccount, WithdrawalRequest

# Register your models here.


class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'bank_name', 'account_number', 'account_holder_name',
                'last_name', 'iban', 'country')
    search_fields = ('user', 'bank_name', 'account_number', 'account_holder_name',
                     'last_name', 'iban', 'country')


class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'bank_account', 'amount', 'status',
                    'request_date', 'currency', 'description')
    search_fields = ('user', 'bank_account', 'amount', 'status',
                     'approved_by', 'request_date', 'currency', 'description')
    list_filter = ('status',)


admin.site.register(BankAccount, BankAccountAdmin)
admin.site.register(WithdrawalRequest, WithdrawalRequestAdmin)
