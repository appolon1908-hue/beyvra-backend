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

    def test_reorder_watchlist_items_optimistic_concurrency_conflict(self):
        res = self.client.patch(
            f"/api/v1/watchlists/{self.watchlist.id}/items/reorder",
            {"expected_version": 99, "ordered_item_ids": [str(self.item2.id), str(self.item1.id)]},
            format="json",
            HTTP_IF_MATCH='"99"'
        )
        self.assertEqual(res.status_code, 412)
