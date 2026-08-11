from django.utils.dateparse import parse_date
from rest_framework import generics, permissions, response, status, views

from .models import CalendarSession, CorporateAction, Instrument, MarketStatusRecord
from .reconciliation import run_reference_data_reconciliation
from .serializers import CalendarSessionSerializer, CorporateActionSerializer, InstrumentSerializer, MarketStatusSerializer


class InstrumentListView(generics.ListAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = InstrumentSerializer

    def get_queryset(self):
        queryset = Instrument.objects.select_related("venue", "calendar").prefetch_related("versions", "provider_mappings")
        asset_class = self.request.query_params.get("asset_class")
        status_value = self.request.query_params.get("status")
        if asset_class:
            queryset = queryset.filter(asset_class=asset_class.upper())
        if status_value:
            queryset = queryset.filter(status=status_value.upper())
        return queryset


class InstrumentDetailView(generics.RetrieveAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = InstrumentSerializer
    lookup_field = "instrument_id"
    queryset = Instrument.objects.select_related("venue", "calendar").prefetch_related("versions", "provider_mappings")


class CalendarView(generics.ListAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = CalendarSessionSerializer

    def get_queryset(self):
        queryset = CalendarSession.objects.select_related("calendar")
        calendar = self.request.query_params.get("calendar")
        start = parse_date(self.request.query_params.get("from", ""))
        end = parse_date(self.request.query_params.get("to", ""))
        if calendar:
            queryset = queryset.filter(calendar__code=calendar.upper())
        if start:
            queryset = queryset.filter(session_date__gte=start)
        if end:
            queryset = queryset.filter(session_date__lte=end)
        return queryset


class CorporateActionListView(generics.ListAPIView):
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = CorporateActionSerializer

    def get_queryset(self):
        queryset = CorporateAction.objects.select_related("instrument")
        instrument_id = self.request.query_params.get("instrument_id")
        if instrument_id:
            queryset = queryset.filter(instrument_id=instrument_id)
        return queryset


class MarketStatusView(views.APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        instrument_id = request.query_params.get("instrument_id")
        if not instrument_id:
            return response.Response({"code": "VALIDATION_FAILED"}, status=status.HTTP_400_BAD_REQUEST)
        record = MarketStatusRecord.objects.filter(instrument_id=instrument_id).first()
        if record is None:
            return response.Response({"code": "MARKET_STATUS_UNAVAILABLE"}, status=status.HTTP_404_NOT_FOUND)
        return response.Response(MarketStatusSerializer(record).data)


class ReconciliationView(views.APIView):
    permission_classes = (permissions.IsAdminUser,)

    def get(self, request):
        report = run_reference_data_reconciliation()
        return response.Response(report, status=status.HTTP_200_OK if report["status"] == "PASS" else status.HTTP_409_CONFLICT)
