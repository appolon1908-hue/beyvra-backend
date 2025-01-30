from django.contrib import admin
from django.db.models.signals import post_save
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from users.models import KYC, KYCFile, User, UserDeviceInfo, AdminSettings
from users.resources import UserResource
from users.signals import update_user_upon_creation

admin.site.site_header = "FX Portal Administration"


class CustomUserAdmin(ImportExportModelAdmin):
    # Disconnect the post_save signal to avoid sending email
    post_save.disconnect(update_user_upon_creation, sender=User, dispatch_uid="update_user_upon_creation")

    resource_class = UserResource  # Attach the UserResource for import/export validation
    list_display = (
        "email",
        "is_staff",
        "is_active",
    )
    list_filter = (
        "email",
        "is_staff",
        "is_active",
    )
    fieldsets = (
        (None, {"fields": ("trader_id", "email", "password")}),
        (
            None,
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "phone_number",
                    "dob",
                    "profile_picture",
                    "address",
                    "gender",
                    "email_verified",
                    "phone_verified",
                    "two_factor_authentication_enabled",
                    "hidden_account_balances_toggle_enabled",
                    "one_click_trade_toggle_enabled",
                    "one_click_trade_closing_toggle_enabled",
                    "is_walkthrough",
                    "role",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_staff",
                    "is_active",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                ),
            },
        ),
        (
            None,
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "phone_number",
                    "profile_picture",
                    "address",
                    "gender",
                    "email_verified",
                    "phone_verified",
                    "two_factor_authentication_enabled",
                    "hidden_account_balances_toggle_enabled",
                    "one_click_trade_toggle_enabled",
                    "one_click_trade_closing_toggle_enabled",
                    "is_walkthrough",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_staff",
                    "is_active",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
    )
    search_fields = ("email",)
    ordering = ("email",)
    readonly_fields = ("trader_id",)


admin.site.register(User, CustomUserAdmin)
admin.site.register(UserDeviceInfo)


@admin.register(KYC)
class KYCAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "status",
        "full_name",
        "id_type",
        "id_number",
        "verified",
        "created_at",
        "view_files",
    ]
    list_filter = ["verified", "created_at"]
    search_fields = ["user__username", "full_name", "id_number"]
    actions = ["mark_as_verified"]

    def mark_as_verified(self, request, queryset):
        queryset.update(verified=True)

    def view_files(self, obj):
        links = [
            f'<a href="/admin/users/kycfile/{kycfile.id}/change/">{kycfile.desc}</a>' for kycfile in obj.files.all()
        ]
        return format_html(", ".join(links))

    view_files.short_description = "KYC files"

    mark_as_verified.short_description = "Mark selected KYCs as verified"


@admin.register(KYCFile)
class KYCFileAdmin(admin.ModelAdmin):
    list_display = ["kyc", "file", "desc"]


@admin.register(AdminSettings)
class AdminSettingsAdmin(admin.ModelAdmin):
    list_display = ('time_zone', 'date_format')  # Fields to display in the list view
    list_editable = ('date_format',)            # Fields editable directly in the list view
    list_display_links = ('time_zone',)         # Field that acts as a link to the detail page
