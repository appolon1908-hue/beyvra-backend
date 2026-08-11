from rest_framework import serializers

from .models import CalendarSession, CorporateAction, Instrument, InstrumentVersion, MarketStatusRecord, ProviderSymbolMapping


class InstrumentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstrumentVersion
        fields = ("version", "canonical_symbol", "name", "status", "tick_size", "lot_size", "metadata", "effective_from", "effective_to")


class ProviderMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderSymbolMapping
        fields = ("provider_id", "product", "provider_symbol", "effective_from", "effective_to")


class InstrumentSerializer(serializers.ModelSerializer):
    venue = serializers.CharField(source="venue.code", allow_null=True)
    calendar = serializers.CharField(source="calendar.code")
    current_version = serializers.SerializerMethodField()

    class Meta:
        model = Instrument
        fields = ("instrument_id", "canonical_symbol", "name", "asset_class", "currency", "venue", "calendar", "status", "isin", "cusip", "figi", "tick_size", "lot_size", "current_version")

    def get_current_version(self, obj):
        version = obj.versions.filter(effective_to__isnull=True).first()
        return InstrumentVersionSerializer(version).data if version else None

class CalendarSessionSerializer(serializers.ModelSerializer):
    calendar = serializers.CharField(source="calendar.code")

    class Meta:
        model = CalendarSession
        fields = ("calendar", "session_date", "kind", "opens_at", "closes_at", "reason")


class CorporateActionSerializer(serializers.ModelSerializer):
    instrument_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CorporateAction
        fields = ("action_id", "instrument_id", "action_type", "announced_at", "effective_at", "source_provider", "source_reference", "terms", "supersedes_id")


class MarketStatusSerializer(serializers.ModelSerializer):
    instrument_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = MarketStatusRecord
        fields = ("instrument_id", "status", "effective_at", "observed_at", "reason")
