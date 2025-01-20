from django.contrib import admin
from security import models

# Register your models here.


class UserActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "anonymous_user", "action_type", "description", "action_status", "created_at")
    list_filter = ("action_type", "action_status")
    search_fields = ("user__email", "ip_address", "user_agent")


admin.site.register(models.UserActivity, UserActivityAdmin)


class IPWhitelistAdmin(admin.ModelAdmin):
    list_display = ("ip_address", "created_at")
    search_fields = ("ip_address",)


admin.site.register(models.IPWhitelist, IPWhitelistAdmin)


class CountryWhitelistAdmin(admin.ModelAdmin):
    list_display = ("country", "created_at")
    search_fields = ("country",)


admin.site.register(models.CountryWhitelist, CountryWhitelistAdmin)


class IPRestrictionsAdmin(admin.ModelAdmin):
    list_display = ("admin", "restriction_type")
    search_fields = ("admin__email", "restriction_type")
    filter_horizontal = ("ip_whitelist", "country_whitelist", "ip_blacklist")


admin.site.register(models.IPRestrictions, IPRestrictionsAdmin)
