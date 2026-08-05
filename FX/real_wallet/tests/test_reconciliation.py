from unittest.mock import patch

from django.test import TestCase

from integrations.models import Organization, OrganizationMembership
from real_wallet.models import Asset, AssetBalance, AssetNetwork, Network, RealWallet
from real_wallet.reconciliation import run_balance_reconciliation
from users.models import User


class ReconciliationTests(TestCase):
    def test_reconciliation_records_match_and_exception_without_mutating_balance(self):
        with patch("users.signals.async_send_welcome_email.delay"):
            user = User.objects.create(email="recon@example.com", phone_number="+12025550002")
        tenant = Organization.objects.create(name="Recon tenant")
        OrganizationMembership.objects.create(user=user, organization=tenant)
        wallet = RealWallet.objects.create(tenant=tenant, owner=user)
        asset = Asset.objects.create(symbol="REC", name="Recon Asset", decimals=6)
        network = Network.objects.create(code="recon-net", name="Recon Network")
        pair = AssetNetwork.objects.create(asset=asset, network=network)
        balance = AssetBalance.objects.create(wallet=wallet, asset_network=pair, posted_atomic="100")
        key = (str(asset.id), str(network.id))
        run = run_balance_reconciliation(tenant=tenant, external_balances={key: "90"})
        balance.refresh_from_db()
        self.assertEqual(run.status, "EXCEPTIONS")
        self.assertEqual(run.items.get().result, "AMOUNT_MISMATCH")
        self.assertEqual(balance.posted_atomic, 100)
