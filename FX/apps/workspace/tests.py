from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from integrations.models import Organization, OrganizationMembership
from reference_data.models import Instrument, TradingCalendar, Venue
from users.models import User

from .models import Watchlist


class WatchlistApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="workspace@example.test", password="safe-password")
        self.other = User.objects.create_user(email="workspace-other@example.test", password="safe-password")
        self.organization = Organization.objects.create(name="Workspace Tenant")
        self.other_organization = Organization.objects.create(name="Other Workspace Tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.organization)
        OrganizationMembership.objects.create(user=self.user, organization=self.other_organization)
        OrganizationMembership.objects.create(user=self.other, organization=self.organization)
        calendar = TradingCalendar.objects.create(
            code="CRYPTO-24X7",
            name="Continuous crypto",
            timezone="UTC",
            continuous=True,
        )
        self.instrument = Instrument.objects.create(
            canonical_symbol="BTC-USD",
            name="Bitcoin / US Dollar",
            asset_class=Instrument.AssetClass.CRYPTO,
            currency="USD",
            calendar=calendar,
            tick_size="0.01",
            lot_size="0.0001",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.headers = {"HTTP_X_ORGANIZATION_ID": str(self.organization.id)}

    def test_default_watchlist_and_symbol_resolution(self):
        created = self.client.post("/api/v1/watchlists", {"name": " My   Markets "}, format="json", **self.headers)
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["is_default"])
        watchlist_id = created.json()["id"]

        item = self.client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            {"instrument_id": "btc-usd"},
            format="json",
            **self.headers,
        )
        self.assertEqual(item.status_code, 201)
        self.assertEqual(item.json()["instrument_id"], str(self.instrument.instrument_id))
        self.assertEqual(item.json()["symbol"], "BTC-USD")

        replay = self.client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            {"instrument_id": str(self.instrument.instrument_id)},
            format="json",
            **self.headers,
        )
        self.assertEqual(replay.status_code, 200)

    def test_watchlists_are_user_and_tenant_scoped(self):
        first = self.client.post("/api/v1/watchlists", {"name": "Primary"}, format="json", **self.headers)
        self.assertEqual(first.status_code, 201)
        other_tenant = self.client.get(
            "/api/v1/watchlists",
            HTTP_X_ORGANIZATION_ID=str(self.other_organization.id),
        )
        self.assertEqual(other_tenant.json()["results"], [])

        other_client = APIClient()
        other_client.force_authenticate(self.other)
        response = other_client.get(
            f"/api/v1/watchlists/{first.json()['id']}",
            HTTP_X_ORGANIZATION_ID=str(self.organization.id),
        )
        self.assertEqual(response.status_code, 404)

    def test_watchlist_names_are_unique_without_case_bypass(self):
        first = self.client.post("/api/v1/watchlists", {"name": "Markets"}, format="json", **self.headers)
        self.assertEqual(first.status_code, 201)
        duplicate = self.client.post("/api/v1/watchlists", {"name": "markets"}, format="json", **self.headers)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["error"]["code"], "WATCHLIST_ALREADY_EXISTS")

    def test_deleting_default_promotes_oldest_remaining_watchlist(self):
        first = self.client.post("/api/v1/watchlists", {"name": "First"}, format="json", **self.headers).json()
        second = self.client.post("/api/v1/watchlists", {"name": "Second"}, format="json", **self.headers).json()
        deleted = self.client.delete(f"/api/v1/watchlists/{first['id']}", **self.headers)
        self.assertEqual(deleted.status_code, 204)
        self.assertTrue(Watchlist.objects.get(pk=second["id"]).is_default)

    def test_unknown_instrument_is_rejected_without_fabrication(self):
        watchlist_id = self.client.post("/api/v1/watchlists", {"name": "Primary"}, format="json", **self.headers).json()["id"]
        response = self.client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            {"instrument_id": "FAKE-USD"},
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_ambiguous_symbol_requires_the_canonical_uuid(self):
        venue = Venue.objects.create(code="SECOND", name="Second venue")
        Instrument.objects.create(
            canonical_symbol="BTC-USD",
            name="Venue-specific Bitcoin / US Dollar",
            asset_class=Instrument.AssetClass.CRYPTO,
            currency="USD",
            venue=venue,
            calendar=self.instrument.calendar,
            tick_size="0.01",
            lot_size="0.0001",
        )
        watchlist_id = self.client.post(
            "/api/v1/watchlists",
            {"name": "Primary"},
            format="json",
            **self.headers,
        ).json()["id"]
        response = self.client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            {"instrument_id": "BTC-USD"},
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("INSTRUMENT_AMBIGUOUS", str(response.json()))
