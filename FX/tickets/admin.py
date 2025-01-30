from django.contrib import admin
from tickets import models

# Register your models here.


class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "message", "updated_at")
    search_fields = ("id", "user", "assigned_admin")


admin.site.register(models.SupportTicket, SupportTicketAdmin)
