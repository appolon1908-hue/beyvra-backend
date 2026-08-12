from django.contrib import admin

from .models import CalendarSession, CorporateAction, Instrument, InstrumentVersion, MarketDataObservation, MarketStatusRecord, ProviderSymbolMapping, ReferenceDataAudit, TradingCalendar, Venue


for model in (Venue, TradingCalendar, CalendarSession, Instrument, InstrumentVersion, ProviderSymbolMapping, CorporateAction, MarketStatusRecord, MarketDataObservation, ReferenceDataAudit):
    admin.site.register(model)
