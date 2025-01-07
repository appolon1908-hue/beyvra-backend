from django.contrib import admin
from .models import Asset, AssetBalance, AssetProfitLoss, AssetType

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'number_of_shares', 'initial_price', 'current_price', 'asset_type', 'user')
    search_fields = ('name', 'asset_type__name', 'user__username')
    list_filter = ('asset_type__name',)

@admin.register(AssetBalance)
class AssetBalanceAdmin(admin.ModelAdmin):
    list_display = ('asset', 'current_balance')
    search_fields = ('asset__name',)
    list_filter = ('asset__asset_type__name',)

@admin.register(AssetProfitLoss)
class AssetProfitLossAdmin(admin.ModelAdmin):
    list_display = ('asset', 'profit_loss')
    search_fields = ('asset__name',)
    list_filter = ('asset__asset_type__name',)

@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    list_filter = ('name',)
