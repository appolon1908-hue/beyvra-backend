from django.contrib import admin

from .models import Asset, AssetType, Trade, TradeCategory


@admin.register(AssetType)
class AssetTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(TradeCategory)
class TradeCategoryAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("name", "symbol", "asset_type")
    search_fields = ("name", "symbol")
    list_filter = ("asset_type",)


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "wallet",
        "asset",
        "quantity",
        "price_per_unit",
        "trade_type",
        "total_value",
        "duration",
        "category",
        "is_active",
        "created_at",
    )
    search_fields = ("wallet__user__email", "asset__name", "trade_type")
    list_filter = (
        "trade_type",
        "created_at",
        "asset__asset_type",
        "category__name",
        "is_active",
    )
    date_hierarchy = "created_at"

    def total_value(self, obj):
        return obj.total_value

    total_value.short_description = "Total Value"
