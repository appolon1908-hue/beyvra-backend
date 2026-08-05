import tempfile
from pathlib import Path

from django.test import TestCase, override_settings
from unittest.mock import patch
from rest_framework.test import APIClient

from integrations.models import Organization, OrganizationMembership
from real_wallet.models import Asset, AssetBalance, AssetNetwork, Deposit, FeatureFlag, LedgerAccount, Network, RealWallet, WithdrawalAddress
from real_wallet.models import WebhookSubscription
from real_wallet.services import (
    IdempotencyConflict,
    create_webhook_delivery,
    enqueue_outbox,
    post_transaction,
    request_withdrawal,
    create_internal_transfer,
    credit_deposit,
    cancel_withdrawal,
    complete_withdrawal,
    fail_withdrawal,
    record_detected_deposit,
    reserve_idempotency,
)
from users.models import User


class RealWalletBoundaryTests(TestCase):
    def setUp(self):
        with patch("users.signals.async_send_welcome_email.delay"):
            self.user = User.objects.create_user(
                email="real-wallet@example.com", password="pass12345", phone_number="+12025550999"
            )
        self.org = Organization.objects.create(name="Real wallet test tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.org)
        self.asset = Asset.objects.create(symbol="TST", name="Test Asset", decimals=6)
        self.debit = LedgerAccount.objects.create(
            tenant=self.org, owner_type="PLATFORM", asset=self.asset,
            account_code="DEPOSIT_CLEARING", account_type="CLEARING", normal_side="DEBIT"
        )
        self.credit = LedgerAccount.objects.create(
            tenant=self.org, owner_type="CUSTOMER", asset=self.asset,
            account_code="CUSTOMER_AVAILABLE", account_type="LIABILITY", normal_side="CREDIT"
        )

    def test_real_wallet_routes_are_disabled_without_demo_fallback(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/v1/wallets/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "FEATURE_DISABLED")

    def test_public_configuration_exposes_only_enabled_reference_data(self):
        Network.objects.create(code="hidden", name="Hidden", enabled=False)
        visible = Network.objects.create(code="visible", name="Visible", enabled=True)
        self.asset.enabled = True
        self.asset.save(update_fields=["enabled"])
        AssetNetwork.objects.create(asset=self.asset, network=visible, enabled=True)
        client = APIClient()
        assets = client.get("/api/v1/assets/")
        networks = client.get("/api/v1/networks/")
        pairs = client.get("/api/v1/asset-networks/")
        self.assertEqual(assets.status_code, 200)
        self.assertEqual([item["symbol"] for item in assets.data["results"]], ["TST"])
        self.assertEqual([item["code"] for item in networks.data["results"]], ["visible"])
        self.assertEqual(len(pairs.data["results"]), 1)

    def test_enabled_read_is_tenant_scoped(self):
        wallet = RealWallet.objects.create(tenant=self.org, owner=self.user)
        with patch("users.signals.async_send_welcome_email.delay"):
            other_user = User.objects.create_user(
                email="other-real-wallet@example.com", password="pass12345", phone_number="+12025550998"
            )
        other_org = Organization.objects.create(name="Other tenant")
        OrganizationMembership.objects.create(user=other_user, organization=other_org)
        RealWallet.objects.create(tenant=other_org, owner=other_user)
        FeatureFlag.objects.filter(key="real_wallet_read_enabled").update(enabled=True)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/v1/wallets/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["results"]], [str(wallet.id)])

    def test_balance_read_exposes_atomic_strings_and_available_projection(self):
        wallet = RealWallet.objects.create(tenant=self.org, owner=self.user)
        network = Network.objects.create(code="synthetic", name="Synthetic")
        pair = AssetNetwork.objects.create(asset=self.asset, network=network)
        AssetBalance.objects.create(
            wallet=wallet, asset_network=pair, posted_atomic="1000000",
            pending_credit_atomic="200000", held_atomic="100000", reserved_atomic="50000",
        )
        FeatureFlag.objects.filter(key="real_wallet_read_enabled").update(enabled=True)
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get(f"/api/v1/wallets/{wallet.id}/balances/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["available_atomic"], "850000")
        self.assertIsInstance(response.data["results"][0]["posted_atomic"], str)

    def test_withdrawal_request_holds_funds_and_writes_outbox_when_enabled(self):
        wallet = RealWallet.objects.create(tenant=self.org, owner=self.user)
        network = Network.objects.create(code="withdrawal-synthetic", name="Synthetic")
        pair = AssetNetwork.objects.create(asset=self.asset, network=network)
        AssetBalance.objects.create(wallet=wallet, asset_network=pair, posted_atomic="1000")
        address = WithdrawalAddress.objects.create(
            tenant=self.org, wallet=wallet, asset_network=pair, address="synthetic-destination",
            status="ACTIVE", risk_state="CLEARED",
        )
        FeatureFlag.objects.filter(key="real_wallet_withdrawals_enabled").update(enabled=True)
        withdrawal = request_withdrawal(
            tenant=self.org, actor=self.user, wallet=wallet, withdrawal_address=address.id,
            amount_atomic="250", idempotency_key="withdrawal-1", request_payload={"amount_atomic": "250"},
        )
        balance = wallet.balances.get(asset_network=pair)
        self.assertEqual(withdrawal.state, "REQUESTED")
        self.assertEqual(balance.held_atomic, 250)
        self.assertEqual(withdrawal.hold.state, "ACTIVE")

    def test_withdrawal_failure_releases_hold_and_completion_captures_once(self):
        wallet = RealWallet.objects.create(tenant=self.org, owner=self.user)
        network = Network.objects.create(code="withdrawal-lifecycle", name="Synthetic")
        pair = AssetNetwork.objects.create(asset=self.asset, network=network)
        balance = AssetBalance.objects.create(wallet=wallet, asset_network=pair, posted_atomic="1000")
        address = WithdrawalAddress.objects.create(
            tenant=self.org, wallet=wallet, asset_network=pair, address="synthetic-lifecycle",
            status="ACTIVE", risk_state="CLEARED",
        )
        FeatureFlag.objects.filter(key="real_wallet_withdrawals_enabled").update(enabled=True)
        withdrawal = request_withdrawal(
            tenant=self.org, actor=self.user, wallet=wallet, withdrawal_address=address.id,
            amount_atomic="200", idempotency_key="withdrawal-failure", request_payload={"amount_atomic": "200"},
        )
        failed = fail_withdrawal(withdrawal_id=withdrawal.id, reason="synthetic provider timeout")
        balance.refresh_from_db()
        self.assertEqual(failed.state, "FAILED")
        self.assertEqual(balance.held_atomic, 0)

        withdrawal = request_withdrawal(
            tenant=self.org, actor=self.user, wallet=wallet, withdrawal_address=address.id,
            amount_atomic="200", idempotency_key="withdrawal-complete", request_payload={"amount_atomic": "200"},
        )
        withdrawal.state = "BROADCAST"
        withdrawal.save(update_fields=["state"])
        completed = complete_withdrawal(withdrawal_id=withdrawal.id, blockchain_transaction="chain-tx-1")
        balance.refresh_from_db()
        self.assertEqual(completed.state, "COMPLETED")
        self.assertEqual(balance.posted_atomic, 800)
        self.assertEqual(balance.held_atomic, 0)
        self.assertEqual(complete_withdrawal(withdrawal_id=withdrawal.id, blockchain_transaction="chain-tx-1").id, withdrawal.id)

    def test_internal_transfer_is_double_entry_and_tenant_scoped(self):
        source = RealWallet.objects.create(tenant=self.org, owner=self.user)
        with patch("users.signals.async_send_welcome_email.delay"):
            destination_user = User.objects.create_user(
                email="destination-real-wallet@example.com", password="pass12345", phone_number="+12025550997"
            )
        OrganizationMembership.objects.create(user=destination_user, organization=self.org)
        destination = RealWallet.objects.create(tenant=self.org, owner=destination_user)
        network = Network.objects.create(code="transfer-synthetic", name="Synthetic")
        pair = AssetNetwork.objects.create(asset=self.asset, network=network)
        source_balance = AssetBalance.objects.create(wallet=source, asset_network=pair, posted_atomic="900")
        destination_balance = AssetBalance.objects.create(wallet=destination, asset_network=pair, posted_atomic="100")
        FeatureFlag.objects.filter(key="real_wallet_internal_transfers_enabled").update(enabled=True)
        transfer = create_internal_transfer(
            tenant=self.org, actor=self.user, source_wallet=source, destination_wallet=destination,
            asset_network=pair, amount_atomic="300", idempotency_key="transfer-1", request_payload={"amount_atomic": "300"},
        )
        source_balance.refresh_from_db()
        destination_balance.refresh_from_db()
        self.assertEqual(transfer.state, "COMPLETED")
        self.assertEqual(source_balance.posted_atomic, 600)
        self.assertEqual(destination_balance.posted_atomic, 400)
        self.assertEqual(transfer.id, create_internal_transfer(
            tenant=self.org, actor=self.user, source_wallet=source, destination_wallet=destination,
            asset_network=pair, amount_atomic="300", idempotency_key="transfer-1", request_payload={"amount_atomic": "300"},
        ).id)

    def test_deposit_detection_is_idempotent_and_credit_requires_confirmations(self):
        wallet = RealWallet.objects.create(tenant=self.org, owner=self.user)
        network = Network.objects.create(code="deposit-synthetic", name="Synthetic")
        pair = AssetNetwork.objects.create(asset=self.asset, network=network)
        FeatureFlag.objects.filter(key="real_wallet_deposits_enabled").update(enabled=True)
        deposit = record_detected_deposit(
            tenant=self.org, wallet=wallet, asset_network=pair, transaction_hash="tx-1",
            output_index=0, amount_atomic="500", confirmations=1,
        )
        replay = record_detected_deposit(
            tenant=self.org, wallet=wallet, asset_network=pair, transaction_hash="tx-1",
            output_index=0, amount_atomic="500", confirmations=1,
        )
        self.assertEqual(deposit.id, replay.id)
        with self.assertRaises(ValueError):
            credit_deposit(deposit_id=deposit.id, required_confirmations=2)
        deposit.confirmations = 2
        deposit.save(update_fields=["confirmations"])
        credited = credit_deposit(deposit_id=deposit.id, required_confirmations=2)
        self.assertEqual(credited.state, "CREDITED")
        self.assertEqual(credited.wallet.balances.get(asset_network=pair).posted_atomic, 500)

    def test_webhook_subscription_returns_secret_once_and_stores_ciphertext(self):
        with tempfile.TemporaryDirectory() as directory:
            key_file = Path(directory) / "webhook-master.key"
            key_file.write_bytes(b"w" * 32)
            with override_settings(REAL_WALLET_WEBHOOK_MASTER_KEY_FILE=str(key_file)):
                client = APIClient()
                client.force_authenticate(self.user)
                response = client.post(
                    "/api/v1/webhook-subscriptions/",
                    {"endpoint": "https://example.com/codestra", "description": "Synthetic receiver"},
                    format="json",
                )
                rotate = client.post(
                    f"/api/v1/webhook-subscriptions/{response.data['id']}/rotate-secret/",
                    {}, format="json",
                )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(rotate.status_code, 200)
        self.assertTrue(response.data["secret_displayed_once"])
        secret = response.data["secret"]
        self.assertTrue(secret.startswith("whsec_"))
        from real_wallet.models import WebhookSecretVersion
        stored = WebhookSecretVersion.objects.filter(subscription_id=response.data["id"])
        self.assertEqual(stored.count(), 2)
        self.assertNotIn(secret.encode(), stored.first().ciphertext)
        self.assertTrue(stored.filter(expires_at__isnull=False).exists())

    def test_balanced_ledger_is_idempotent(self):
        kwargs = {
            "tenant": self.org, "transaction_type": "TEST", "idempotency_key": "ledger-test-1",
            "entries": [
                {"account": self.debit, "asset": self.asset, "direction": "DEBIT", "amount_atomic": "100"},
                {"account": self.credit, "asset": self.asset, "direction": "CREDIT", "amount_atomic": "100"},
            ],
        }
        first = post_transaction(**kwargs)
        second = post_transaction(**kwargs)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.entries.count(), 2)

    def test_unbalanced_ledger_is_rejected(self):
        with self.assertRaises(ValueError):
            post_transaction(
                tenant=self.org, transaction_type="TEST", idempotency_key="unbalanced",
                entries=[{"account": self.debit, "asset": self.asset, "direction": "DEBIT", "amount_atomic": "1"}],
            )

    def test_real_wallet_has_no_demo_wallet_foreign_key(self):
        field_models = {field.related_model for field in RealWallet._meta.fields if field.is_relation}
        self.assertNotIn("wallet.Wallet", {model._meta.label for model in field_models})

    def test_large_atomic_amount_is_supported_without_float(self):
        amount = "9" * 60
        tx = post_transaction(
            tenant=self.org,
            transaction_type="LARGE_AMOUNT",
            idempotency_key="large-amount",
            entries=[
                {"account": self.debit, "asset": self.asset, "direction": "DEBIT", "amount_atomic": amount},
                {"account": self.credit, "asset": self.asset, "direction": "CREDIT", "amount_atomic": amount},
            ],
        )
        self.assertEqual(tx.entries.count(), 2)
        self.assertEqual(tx.entries.first().amount_atomic.as_tuple().exponent, 0)

    def test_idempotency_conflict_is_rejected_in_postgres_boundary(self):
        first, created = reserve_idempotency(
            tenant=self.org, actor=self.user, endpoint="/withdrawals", method="POST",
            key="same-key", request_payload={"amount_atomic": "10"},
        )
        self.assertTrue(created)
        replay, created = reserve_idempotency(
            tenant=self.org, actor=self.user, endpoint="/withdrawals", method="POST",
            key="same-key", request_payload={"amount_atomic": "10"},
        )
        self.assertFalse(created)
        self.assertEqual(first.pk, replay.pk)
        with self.assertRaises(IdempotencyConflict):
            reserve_idempotency(
                tenant=self.org, actor=self.user, endpoint="/withdrawals", method="POST",
                key="same-key", request_payload={"amount_atomic": "11"},
            )

    def test_outbox_and_webhook_delivery_are_deduplicated(self):
        event = enqueue_outbox(
            tenant=self.org, aggregate_type="wallet", aggregate_id=self.org.id,
            event_type="wallet.created", payload={"synthetic": True},
        )
        self.assertIsNone(event.published_at)
        subscription = WebhookSubscription.objects.create(
            tenant=self.org, endpoint="https://example.com/webhooks", status="DISABLED"
        )
        first, first_created = create_webhook_delivery(
            tenant=self.org, subscription=subscription, event_id="evt-1",
            event_type="wallet.created", payload={"synthetic": True},
        )
        replay, replay_created = create_webhook_delivery(
            tenant=self.org, subscription=subscription, event_id="evt-1",
            event_type="wallet.created", payload={"synthetic": True},
        )
        self.assertTrue(first_created)
        self.assertFalse(replay_created)
        self.assertEqual(first.pk, replay.pk)
