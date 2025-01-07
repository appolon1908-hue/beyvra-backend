from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from wallet.models import Currency, Transaction, Wallet, ManualBalanceUpdate


class WalletAdmin(admin.ModelAdmin):
    list_display = ["user", "name", "balance"]
    search_fields = ["user"]
    list_filter = ["name"]

    class Meta:
        model = Wallet


admin.site.register(Wallet, WalletAdmin)


class TransactionAdmin(admin.ModelAdmin):
    list_display = ["wallet", "type", "amount", "status"]
    list_filter = ["type", "status"]

    class Meta:
        model = Transaction


admin.site.register(Transaction, TransactionAdmin)


class CurrencyResource(resources.ModelResource):
    class Meta:
        model = Currency


class CurrencyAdmin(ImportExportModelAdmin):
    list_display = ["name", "symbol", "longer_name"]
    search_fields = ["name"]
    resource_class = CurrencyResource


admin.site.register(Currency, CurrencyAdmin)


admin.site.register(ManualBalanceUpdate)