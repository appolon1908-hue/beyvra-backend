from django.test import TestCase
from unittest.mock import patch

from integrations.models import Organization, OrganizationMembership
from real_wallet.compliance import ComplianceRestrictionError, approve_screening, check_wallet_permission, screen_transaction
from real_wallet.models import Asset, AssetNetwork, ComplianceProfile, Network, RealWallet, Restriction
from real_wallet.providers import DisabledCustodyAdapter, ProviderUnavailable, SandboxChainAdapter
from users.models import User


class ComplianceAndProviderTests(TestCase):
    def setUp(self):
        with patch("users.signals.async_send_welcome_email.delay"):
            self.user = User.objects.create(email="compliance@example.com", phone_number="+12025550001")
        self.org = Organization.objects.create(name="Compliance tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.org)
        self.wallet = RealWallet.objects.create(tenant=self.org, owner=self.user)
        asset = Asset.objects.create(symbol="CMP", name="Compliance Asset", decimals=6)
        network = Network.objects.create(code="compliance-net", name="Compliance Network")
        self.pair = AssetNetwork.objects.create(asset=asset, network=network)

    def test_wallet_permission_requires_approved_profile_and_no_restriction(self):
        with self.assertRaises(ComplianceRestrictionError):
            check_wallet_permission(tenant=self.org, wallet=self.wallet, action="withdrawal")
        ComplianceProfile.objects.create(tenant=self.org, status="APPROVED")
        self.assertTrue(check_wallet_permission(tenant=self.org, wallet=self.wallet, action="withdrawal"))
        Restriction.objects.create(tenant=self.org, wallet=self.wallet, kind="WITHDRAWAL", reason_code="TEST")
        with self.assertRaises(ComplianceRestrictionError):
            check_wallet_permission(tenant=self.org, wallet=self.wallet, action="withdrawal")

    def test_screening_is_pending_until_review(self):
        screening = screen_transaction(tenant=self.org, asset_network=self.pair, direction="WITHDRAWAL", amount_atomic="10")
        self.assertEqual(screening.status, "PENDING")
        self.assertEqual(approve_screening(screening.id, "synthetic approval").status, "APPROVED")

    def test_disabled_provider_fails_closed_and_sandbox_is_explicit(self):
        with self.assertRaises(ProviderUnavailable):
            DisabledCustodyAdapter().create_address(connection_id="x", asset_network_id="y")
        self.assertTrue(SandboxChainAdapter().validate_address(network_code="x", address="sandbox_address"))
