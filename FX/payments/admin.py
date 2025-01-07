from django.contrib import admin

from .models import PaymentMethod, Payment, PaymentsProvider


class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ["name", "type"]
    search_fields = ["name"]
    list_filter = ["name", "type"]

    class Meta:
        model = PaymentMethod


admin.site.register(PaymentMethod, PaymentMethodAdmin)
admin.site.register(Payment)
admin.site.register(PaymentsProvider)