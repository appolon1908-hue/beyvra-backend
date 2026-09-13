"""Explicit PAPER test reference data, independent of migration seed history."""

from datetime import date

from apps.post_trade.models import SettlementCalendar


def ensure_paper_settlement_calendar():
    return SettlementCalendar.objects.get_or_create(
        code="TEST-PAPER-CRYPTO-INSTANT",
        policy_version="paper-test-v1",
        defaults={
            "asset_class": "CRYPTO",
            "venue_id": "SIMULATED",
            "currency": "USD",
            "settlement_convention": "INSTANT",
            "timezone": "UTC",
            "calendar_ref": "TEST_PAPER_24X7",
            "holidays": [],
            "effective_from": date(2020, 1, 1),
        },
    )[0]
