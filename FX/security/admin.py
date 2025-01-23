from django.contrib import admin
from security import models
from security.custom_filters import CustomActionTypeFilter

# Register your models here.


class UserActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "anonymous_user", "custom_action_type", "description", "action_status", "created_at")
    list_filter = (CustomActionTypeFilter, "action_status")
    search_fields = ("user__email", "ip_address", "user_agent")

    def custom_action_type(self, obj):
        return obj.custom_action_type

    custom_action_type.short_description = "Action Type"


admin.site.register(models.UserActivity, UserActivityAdmin)


class IPWhitelistAdmin(admin.ModelAdmin):
    list_display = ("ip_address", "created_at")
    search_fields = ("ip_address",)


admin.site.register(models.IPWhitelist, IPWhitelistAdmin)


class IPBlacklistAdmin(admin.ModelAdmin):
    list_display = ("ip_address", "created_at")
    search_fields = ("ip_address",)


admin.site.register(models.IPBlacklist, IPBlacklistAdmin)


class CountryWhitelistAdmin(admin.ModelAdmin):
    list_display = ("country", "created_at")
    search_fields = ("country",)


admin.site.register(models.CountryWhitelist, CountryWhitelistAdmin)


class CountryBlacklistAdmin(admin.ModelAdmin):
    list_display = ("country", "created_at")
    search_fields = ("country",)


admin.site.register(models.CountryBlacklist, CountryBlacklistAdmin)


class UserBlacklistAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    search_fields = ("user",)


admin.site.register(models.UserIPBlacklist, UserBlacklistAdmin)


class IPRestrictionsAdmin(admin.ModelAdmin):
    list_display = ("admin", "restriction_type")
    search_fields = ("admin__email", "restriction_type")
    filter_horizontal = (
        "ip_whitelist",
        "country_whitelist",
        "country_blacklist",
        "ip_blacklist",
        "user_ip_blacklist",
    )


admin.site.register(models.IPRestrictions, IPRestrictionsAdmin)
