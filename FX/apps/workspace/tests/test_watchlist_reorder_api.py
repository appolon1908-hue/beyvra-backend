import uuid
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from apps.workspace.models import Watchlist, WatchlistItem
from users.models import User
from integrations.models import Organization, OrganizationMembership


SIMULATION = override_settings(
    DEPLOYMENT_ENV="test",
    SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
)


@SIMULATION
class WatchlistAlertsApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email=f"wl-test-{uuid.uuid4()}@example.invalid",
            phone_number=f"+1202{uuid.uuid4().int % 10000000:07d}",
            password="testpassword"
        )
        self.org = Organization.objects.create(name=f"Org {uuid.uuid4()}")
        OrganizationMembership.objects.create(user=self.user, organization=self.org)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.watchlist = Watchlist.objects.create(
            organization=self.org,
            user=self.user,
            name="Main Watchlist",
            is_default=True
        )
        self.item1 = WatchlistItem.objects.create(watchlist=self.watchlist, instrument_id="BTC-USD", sort_order=0)
        self.item2 = WatchlistItem.objects.create(watchlist=self.watchlist, instrument_id="ETH-USD", sort_order=1)

    def test_reorder_watchlist_items_optimistic_concurrency_success(self):
        res = self.client.patch(
            f"/api/v1/watchlists/{self.watchlist.id}/items/reorder",
            {"expected_version": 1, "ordered_item_ids": [str(self.item2.id), str(self.item1.id)]},
            format="json",
            HTTP_IF_MATCH='"1"'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["ETag"], '"2"')
        self.watchlist.refresh_from_db()
        self.item1.refresh_from_db()
        self.item2.refresh_from_db()
        self.assertEqual(self.watchlist.version, 2)
        self.assertEqual(self.item2.sort_order, 0)
        self.assertEqual(self.item1.sort_order, 1)

    def test_reorder_watchlist_items_optimistic_concurrency_conflict(self):
        res = self.client.patch(
            f"/api/v1/watchlists/{self.watchlist.id}/items/reorder",
            {"expected_version": 99, "ordered_item_ids": [str(self.item2.id), str(self.item1.id)]},
            format="json",
            HTTP_IF_MATCH='"99"'
        )
        self.assertEqual(res.status_code, 412)

    def test_reorder_requires_if_match(self):
        res = self.client.patch(
            f"/api/v1/watchlists/{self.watchlist.id}/items/reorder",
            {"ordered_item_ids": [str(self.item2.id), str(self.item1.id)]},
            format="json",
        )
        self.assertEqual(res.status_code, 428)

    def test_reorder_rejects_duplicate_missing_and_foreign_items(self):
        other_watchlist = Watchlist.objects.create(
            organization=self.org,
            user=self.user,
            name="Other Watchlist",
        )
        foreign = WatchlistItem.objects.create(
            watchlist=other_watchlist,
            instrument_id="SOL-USD",
            sort_order=0,
        )
        cases = [
            [str(self.item1.id), str(self.item1.id)],
            [str(self.item1.id)],
            [str(self.item1.id), str(foreign.id)],
        ]
        for ordered_ids in cases:
            res = self.client.patch(
                f"/api/v1/watchlists/{self.watchlist.id}/items/reorder",
                {"ordered_item_ids": ordered_ids},
                format="json",
                HTTP_IF_MATCH='"1"',
            )
            self.assertEqual(res.status_code, 400, ordered_ids)
        self.watchlist.refresh_from_db()
        self.assertEqual(self.watchlist.version, 1)

    def test_stale_second_reorder_is_rejected(self):
        first = self.client.patch(
            f"/api/v1/watchlists/{self.watchlist.id}/items/reorder",
            {"ordered_item_ids": [str(self.item2.id), str(self.item1.id)]},
            format="json",
            HTTP_IF_MATCH='"1"',
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.patch(
            f"/api/v1/watchlists/{self.watchlist.id}/items/reorder",
            {"ordered_item_ids": [str(self.item1.id), str(self.item2.id)]},
            format="json",
            HTTP_IF_MATCH='"1"',
        )
        self.assertEqual(second.status_code, 412)
