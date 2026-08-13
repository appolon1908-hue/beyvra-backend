from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import User

from .models import CalendarSession, CorporateAction, Instrument, InstrumentVersion, MarketDataObservation, MarketStatusRecord, ProviderSymbolMapping, ReferenceDataAudit, TradingCalendar, Venue
from .reconciliation import run_reference_data_reconciliation
from .services import record_market_observation, resolve_provider_symbol
from ws.gateway import _resolve_realtime_instrument


class ReferenceAuthorityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="reference@example.test", password="safe-test-password")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.calendar = TradingCalendar.objects.create(code="XNYS", name="NYSE", timezone="America/New_York")
        self.venue = Venue.objects.create(code="XNYS", name="New York Stock Exchange", mic="XNYS", timezone="America/New_York", country_code="US")
        self.instrument = Instrument.objects.create(
            canonical_symbol="AAPL.XNYS",
            name="Apple Inc.",
            asset_class=Instrument.AssetClass.EQUITY,
            currency="USD",
            venue=self.venue,
            calendar=self.calendar,
            isin="US0378331005",
            figi="BBG000B9XRY4",
            tick_size=Decimal("0.01"),
            lot_size=Decimal("1"),
        )
        self.effective = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        InstrumentVersion.objects.create(
            instrument=self.instrument,
            version=1,
            canonical_symbol=self.instrument.canonical_symbol,
            name=self.instrument.name,
            status=self.instrument.status,
            tick_size=self.instrument.tick_size,
            lot_size=self.instrument.lot_size,
            effective_from=self.effective,
        )
        self.mapping = ProviderSymbolMapping.objects.create(
            provider_id="massive",
            provider_symbol="AAPL",
            product="MARKET_DATA",
            instrument=self.instrument,
            effective_from=self.effective,
        )

    def test_canonical_identity_and_safe_api_contract(self):
        listing = self.client.get("/api/v1/market/instruments")
        self.assertEqual(listing.status_code, 200)
        row = listing.json()["results"][0]
        self.assertEqual(row["instrument_id"], str(self.instrument.instrument_id))
        self.assertEqual(row["canonical_symbol"], "AAPL.XNYS")
        self.assertNotIn("provider_mappings", row)
        self.assertNotIn("credential", str(row).lower())
        detail = self.client.get(f"/api/v1/market/instruments/{self.instrument.instrument_id}")
        self.assertEqual(detail.status_code, 200)

    def test_market_authority_apis_require_authentication(self):
        anonymous = APIClient()
        for path in ("/api/v1/market/instruments", "/api/v1/market/calendar", "/api/v1/market/corporate-actions"):
            self.assertIn(anonymous.get(path).status_code, (401, 403))

    def test_provider_mapping_is_unique_and_effective_dated(self):
        self.assertEqual(resolve_provider_symbol(provider_id="massive", provider_symbol="AAPL", at=self.effective + timedelta(days=1)).instrument_id, self.instrument.instrument_id)
        with self.assertRaises(Exception):
            ProviderSymbolMapping.objects.create(provider_id="massive", provider_symbol="AAPL", product="MARKET_DATA", instrument=self.instrument, effective_from=self.effective + timedelta(days=1))

    def test_security_identifiers_and_current_version_are_unique(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            Instrument.objects.create(canonical_symbol="DUP.XNYS", name="Duplicate identity", asset_class=Instrument.AssetClass.EQUITY, currency="USD", venue=self.venue, calendar=self.calendar, isin=self.instrument.isin, tick_size=Decimal("0.01"), lot_size=Decimal("1"))
        with self.assertRaises(DatabaseError), transaction.atomic():
            InstrumentVersion.objects.create(instrument=self.instrument, version=2, canonical_symbol="AAPL.XNYS", name="Duplicate current version", status=Instrument.Status.ACTIVE, tick_size=Decimal("0.01"), lot_size=Decimal("1"), effective_from=self.effective + timedelta(days=1))

    def test_historical_provider_mapping_resolves_by_time(self):
        cutoff = self.effective + timedelta(days=30)
        self.mapping.effective_to = cutoff
        self.mapping.save(update_fields=("effective_to",))
        replacement = ProviderSymbolMapping.objects.create(provider_id="massive", provider_symbol="AAPL", product="MARKET_DATA", instrument=self.instrument, effective_from=cutoff)
        self.assertEqual(resolve_provider_symbol(provider_id="massive", provider_symbol="AAPL", at=cutoff - timedelta(seconds=1)).pk, self.mapping.pk)
        self.assertEqual(resolve_provider_symbol(provider_id="massive", provider_symbol="AAPL", at=cutoff).pk, replacement.pk)

    def test_market_data_provenance_and_correction_are_append_only(self):
        first = record_market_observation(provider_id="massive", provider_symbol="AAPL", data_type="QUOTE", provider_event_id="quote-1", observed_at=self.effective + timedelta(days=1), payload_safe={"bid": "190.00", "ask": "190.02"})
        correction = record_market_observation(provider_id="massive", provider_symbol="AAPL", data_type="QUOTE", provider_event_id="quote-1-correction", observed_at=self.effective + timedelta(days=1), payload_safe={"bid": "190.01", "ask": "190.03"}, supersedes=first)
        self.assertEqual(correction.instrument_id, self.instrument.instrument_id)
        self.assertEqual(correction.mapping_id, self.mapping.pk)
        self.assertNotEqual(correction.payload_hash, first.payload_hash)
        self.assertEqual(ReferenceDataAudit.objects.filter(entity_ref=str(first.observation_id)).count(), 1)
        self.assertEqual(ReferenceDataAudit.objects.filter(entity_ref=str(correction.observation_id), event_type="MARKET_DATA_CORRECTED").count(), 1)

    def test_calendar_correctness_and_api_filtering(self):
        session = CalendarSession(calendar=self.calendar, session_date=date(2026, 7, 3), kind=CalendarSession.Kind.EARLY_CLOSE, opens_at=datetime(2026, 7, 3, 13, 30, tzinfo=dt_timezone.utc), closes_at=datetime(2026, 7, 3, 17, 0, tzinfo=dt_timezone.utc), reason="Scheduled early close")
        session.full_clean()
        session.save()
        invalid = CalendarSession(calendar=self.calendar, session_date=date(2026, 7, 4), kind=CalendarSession.Kind.CLOSED, opens_at=timezone.now())
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        result = self.client.get("/api/v1/market/calendar?calendar=XNYS&from=2026-07-01&to=2026-07-31")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["results"][0]["kind"], "EARLY_CLOSE")

    def test_corporate_action_and_market_status_authorities(self):
        action = CorporateAction.objects.create(instrument=self.instrument, action_type=CorporateAction.Type.SPLIT, announced_at=self.effective, effective_at=self.effective + timedelta(days=90), source_provider="massive", source_reference="action-1", terms={"ratio_from": "1", "ratio_to": "4"})
        MarketStatusRecord.objects.create(instrument=self.instrument, status=MarketStatusRecord.Status.OPEN, effective_at=timezone.now(), observed_at=timezone.now(), source_provider="massive", source_reference="status-1")
        actions = self.client.get(f"/api/v1/market/corporate-actions?instrument_id={self.instrument.instrument_id}")
        self.assertEqual(actions.status_code, 200)
        self.assertEqual(actions.json()["results"][0]["action_id"], str(action.action_id))
        market_status = self.client.get(f"/api/v1/market/status?instrument_id={self.instrument.instrument_id}")
        self.assertEqual(market_status.status_code, 200)
        self.assertEqual(market_status.json()["status"], "OPEN")

    def test_tenant_headers_cannot_change_global_reference_identity(self):
        first = self.client.get("/api/v1/market/instruments", HTTP_X_BEYVRA_TENANT="tenant-a").json()
        second = self.client.get("/api/v1/market/instruments", HTTP_X_BEYVRA_TENANT="tenant-b").json()
        self.assertEqual(first, second)

    def test_realtime_resolves_canonical_uuid_through_instrument_authority(self):
        ProviderSymbolMapping.objects.create(
            provider_id="binance",
            provider_symbol="AAPLUSDT",
            product="MARKET_DATA",
            instrument=self.instrument,
            effective_from=self.effective,
        )
        resolved = _resolve_realtime_instrument.__wrapped__(str(self.instrument.instrument_id))
        self.assertEqual(resolved, (str(self.instrument.instrument_id), "AAPLUSDT"))
        self.assertIsNone(_resolve_realtime_instrument.__wrapped__(str(uuid.uuid4())))

    def test_reconciliation_passes_and_detects_missing_current_version(self):
        self.assertEqual(run_reference_data_reconciliation()["status"], "PASS")
        InstrumentVersion.objects.filter(instrument=self.instrument).update(effective_to=timezone.now())
        report = run_reference_data_reconciliation()
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("CURRENT_INSTRUMENT_VERSION_COUNT", {item["check"] for item in report["violations"]})

    def test_reconciliation_endpoint_is_internal_admin_only(self):
        self.assertEqual(self.client.get("/api/v1/internal/reference-data/reconciliation").status_code, 403)
        self.user.is_staff = True
        self.user.save(update_fields=("is_staff",))
        self.assertEqual(self.client.get("/api/v1/internal/reference-data/reconciliation").json()["status"], "PASS")

    def test_provider_mappings_are_staff_only_and_not_public_identity(self):
        path = f"/api/v1/internal/reference-data/provider-mappings/{self.instrument.instrument_id}"
        self.assertEqual(self.client.get(path).status_code, 403)
        self.user.is_staff = True
        self.user.save(update_fields=("is_staff",))
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["provider_symbol"], "AAPL")

    def test_append_only_records_reject_mutation_on_postgresql(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger authority")
        observation = record_market_observation(provider_id="massive", provider_symbol="AAPL", data_type="QUOTE", provider_event_id="quote-immutable", observed_at=self.effective + timedelta(days=1), payload_safe={"last": "190.00"})
        with self.assertRaises(DatabaseError), transaction.atomic():
            MarketDataObservation.objects.filter(pk=observation.pk).update(payload_hash="0" * 64)
