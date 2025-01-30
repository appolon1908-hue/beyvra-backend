from django.contrib import admin
from .models import Transaction, Revenue, UserActivity, Trade, Report

admin.site.register([Transaction, Revenue, UserActivity, Trade, Report])
