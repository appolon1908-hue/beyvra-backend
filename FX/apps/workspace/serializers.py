from rest_framework import serializers

from .instruments import InstrumentResolutionError, resolve_active_instrument
from .models import Watchlist, WatchlistItem


class WatchlistItemSerializer(serializers.ModelSerializer):
    instrument_id = serializers.CharField(max_length=64)
    symbol = serializers.SerializerMethodField()

    class Meta:
        model = WatchlistItem
        fields = ("id", "instrument_id", "symbol", "sort_order", "created_at")
        read_only_fields = ("id", "symbol", "created_at")

    def validate_instrument_id(self, value):
        try:
            instrument = resolve_active_instrument(value)
        except InstrumentResolutionError as exc:
            raise serializers.ValidationError(exc.code) from exc
        return str(instrument.instrument_id)

    def get_symbol(self, obj):
        instrument = Instrument.objects.filter(instrument_id=obj.instrument_id).first()
        return instrument.canonical_symbol if instrument else None


class WatchlistSerializer(serializers.ModelSerializer):
    items = WatchlistItemSerializer(many=True, read_only=True)

    class Meta:
        model = Watchlist
        fields = ("id", "name", "is_default", "items", "created_at", "updated_at")
        read_only_fields = ("id", "is_default", "items", "created_at", "updated_at")

    def validate_name(self, value):
        normalized = " ".join(value.split())
        if not normalized:
            raise serializers.ValidationError("Name is required.")
        return normalized
