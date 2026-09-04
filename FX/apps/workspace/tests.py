import uuid

from django.test import TestCase
from rest_framework.test import APIClient

from apps.foundation.models import ApplicationAuditEvent, IdempotencyRecord
from integrations.models import Organization, OrganizationMembership
from reference_data.models import Instrument, TradingCalendar, Venue
from users.models import User

from .models import Watchlist, WatchlistItem


class WatchlistApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="workspace@example.test",
            password="safe-password",
        )
        self.other = User.objects.create_user(
            email="workspace-other@example.test",
            password="safe-password",
        )
        self.organization = Organization.objects.create(name="Workspace Tenant")
        self.other_organization = Organization.objects.create(
            name="Other Workspace Tenant"
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.organization,
        )
        OrganizationMembership.objects.create(
            user=self.user,
            organization=self.other_organization,
        )
        OrganizationMembership.objects.create(
            user=self.other,
            organization=self.organization,
        )
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
        self.tenant_headers = {
            "HTTP_X_ORGANIZATION_ID": str(self.organization.id)
        }

    def command_headers(self, key, *, tenant_headers=None):
        return {
            **(tenant_headers or self.tenant_headers),
            "HTTP_IDEMPOTENCY_KEY": key,
            "HTTP_X_REQUEST_ID": str(uuid.uuid4()),
        }

    def create_watchlist(self, name="Primary", key=None, *, tenant_headers=None):
        return self.client.post(
            "/api/v1/watchlists",
            {"name": name},
            format="json",
            **self.command_headers(
                key or f"watchlist-create-{uuid.uuid4()}",
                tenant_headers=tenant_headers,
            ),
        )

    def test_default_watchlist_and_canonical_instrument_resolution(self):
        created = self.create_watchlist(" My   Markets ")
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["is_default"])
        self.assertEqual(created.json()["name"], "My Markets")
        self.assertEqual(created.json()["version"], 1)
        watchlist_id = created.json()["id"]

        item = self.client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            {
                "instrument_id": "btc-usd",
                "version": created.json()["version"],
            },
            format="json",
            **self.command_headers("watchlist-item-add"),
        )
        self.assertEqual(item.status_code, 201)
        self.assertEqual(
            item.json()["instrument_id"],
            str(self.instrument.instrument_id),
        )
        self.assertEqual(item.json()["symbol"], "BTC-USD")
        self.assertEqual(item.json()["watchlist_version"], 2)

        replay = self.client.post(
            f"/api/v1/watchlists/{watchlist_id}/items",
            {
                "instrument_id": str(self.instrument.instrument_id),
                "version": 2,
            },
            format="json",
            **self.command_headers("watchlist-item-existing"),
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(WatchlistItem.objects.count(), 1)

    def test_create_is_durably_idempotent_and_semantic_reuse_conflicts(self):
        first = self.create_watchlist("Primary", key="create-once")
        second = self.create_watchlist("Primary", key="create-once")
        conflict = self.create_watchlist("Different", key="create-once")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(Watchlist.objects.count(), 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)
        self.assertEqual(
            ApplicationAuditEvent.objects.filter(
                action="workspace.watchlist.created"
            ).count(),
            1,
        )

    def test_mutations_require_command_identity_and_current_version(self):
        missing_headers = self.client.post(
            "/api/v1/watchlists",
            {"name": "No identity"},
            format="json",
            **self.tenant_headers,
        )
        self.assertEqual(missing_headers.status_code, 400)

        created = self.create_watchlist().json()
        renamed = self.client.patch(
            f"/api/v1/watchlists/{created['id']}",
            {"name": "Renamed", "version": created["version"]},
            format="json",
            **self.command_headers("rename-current"),
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["version"], 2)

        stale = self.client.patch(
            f"/api/v1/watchlists/{created['id']}",
            {"name": "Stale overwrite", "version": 1},
            format="json",
            **self.command_headers("rename-stale"),
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["current_version"], 2)
        self.assertEqual(
            Watchlist.objects.get(pk=created["id"]).name,
            "Renamed",
        )

    def test_watchlists_are_user_and_tenant_scoped(self):
        first = self.create_watchlist().json()
        other_tenant = self.client.get(
            "/api/v1/watchlists",
            HTTP_X_ORGANIZATION_ID=str(self.other_organization.id),
        )
        self.assertEqual(other_tenant.json()["results"], [])

        other_client = APIClient()
        other_client.force_authenticate(self.other)
        response = other_client.get(
            f"/api/v1/watchlists/{first['id']}",
            HTTP_X_ORGANIZATION_ID=str(self.organization.id),
        )
        self.assertEqual(response.status_code, 404)

        invalid_tenant = self.client.get(
            "/api/v1/watchlists",
            HTTP_X_ORGANIZATION_ID=str(uuid.uuid4()),
        )
        self.assertEqual(invalid_tenant.status_code, 403)

    def test_watchlist_names_are_unique_without_case_bypass(self):
        first = self.create_watchlist("Markets")
        duplicate = self.create_watchlist("markets")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            duplicate.json()["error"]["code"],
            "WATCHLIST_ALREADY_EXISTS",
        )

    def test_deleting_default_promotes_oldest_remaining_watchlist(self):
        first = self.create_watchlist("First").json()
        second = self.create_watchlist("Second").json()

        deleted = self.client.delete(
            f"/api/v1/watchlists/{first['id']}",
            {"version": first["version"]},
            format="json",
            **self.command_headers("delete-first"),
        )
        self.assertEqual(deleted.status_code, 204)
        replacement = Watchlist.objects.get(pk=second["id"])
        self.assertTrue(replacement.is_default)
        self.assertEqual(replacement.version, 2)

        replay = self.client.delete(
            f"/api/v1/watchlists/{first['id']}",
            {"version": first["version"]},
            format="json",
            **self.command_headers("delete-first"),
        )
        self.assertEqual(replay.status_code, 204)

    def test_unknown_and_ambiguous_instruments_fail_closed(self):
        watchlist = self.create_watchlist().json()
        unknown = self.client.post(
            f"/api/v1/watchlists/{watchlist['id']}/items",
            {"instrument_id": "FAKE-USD", "version": watchlist["version"]},
            format="json",
            **self.command_headers("add-unknown"),
        )
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(
            unknown.json()["error"]["code"],
            "INSTRUMENT_UNAVAILABLE",
        )

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
        ambiguous = self.client.post(
            f"/api/v1/watchlists/{watchlist['id']}/items",
            {"instrument_id": "BTC-USD", "version": watchlist["version"]},
            format="json",
            **self.command_headers("add-ambiguous"),
        )
        self.assertEqual(ambiguous.status_code, 409)
        self.assertEqual(
            ambiguous.json()["error"]["code"],
            "INSTRUMENT_AMBIGUOUS",
        )

    def test_inactive_instrument_can_still_be_removed_by_canonical_uuid(self):
        watchlist = self.create_watchlist().json()
        added = self.client.post(
            f"/api/v1/watchlists/{watchlist['id']}/items",
            {
                "instrument_id": str(self.instrument.instrument_id),
                "version": watchlist["version"],
            },
            format="json",
            **self.command_headers("add-before-inactive"),
        )
        self.assertEqual(added.status_code, 201)

        self.instrument.status = Instrument.Status.INACTIVE
        self.instrument.save(update_fields=("status",))

        removed = self.client.delete(
            (
                f"/api/v1/watchlists/{watchlist['id']}/items/"
                f"{self.instrument.instrument_id}"
            ),
            {"version": added.json()["watchlist_version"]},
            format="json",
            **self.command_headers("remove-inactive"),
        )
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(WatchlistItem.objects.exists())
