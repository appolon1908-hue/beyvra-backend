from decimal import Decimal
from types import SimpleNamespace

from django.db import IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db import connection
from django.test import TestCase, TransactionTestCase

from apps.trading.application.accounts import (
    ensure_paper_identity,
    serialize_trading_account,
)
from apps.trading.application.simulation import account_for
from apps.trading.models import SimulatedAccount, TradingAccount


class TradingAccountContractTests(TestCase):
    def setUp(self):
        self.user = SimpleNamespace(pk="account-contract-owner")
        self.projection = account_for(self.user, "tenant-a")
        self.account = self.projection.trading_account

    def test_existing_virtual_projection_gets_one_paper_identity(self):
        again = account_for(self.user, "tenant-a")
        self.assertEqual(again.pk, self.projection.pk)
        self.assertEqual(TradingAccount.objects.count(), 1)
        self.assertEqual(self.account.id, self.projection.id)
        self.assertEqual(self.projection.total_balance, Decimal("10000"))
        self.assertEqual(
            serialize_trading_account(self.account),
            {
                "account_id": str(self.projection.id),
                "execution_mode": "PAPER",
                "base_currency": "USD",
                "status": "ACTIVE",
                "trading_enabled": True,
                "funding_enabled": False,
                "withdrawals_enabled": False,
            },
        )

    def test_tenant_and_subject_scopes_do_not_share_identity_or_funds(self):
        other_tenant = account_for(self.user, "tenant-b")
        other_subject = account_for(SimpleNamespace(pk="another-owner"), "tenant-a")
        self.assertEqual(
            len({self.projection.pk, other_tenant.pk, other_subject.pk}), 3
        )
        self.assertEqual(TradingAccount.objects.count(), 3)

    def test_database_rejects_paper_financial_flags_and_invalid_modes(self):
        invalid_changes = (
            {"funding_enabled": True},
            {"withdrawals_enabled": True},
            {"execution_mode": "DEMO"},
            {"execution_mode": "LIVE"},
            {"execution_mode": "OTHER"},
            {"paper_projection": None},
            {"status": "UNKNOWN"},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    TradingAccount.objects.filter(pk=self.account.pk).update(**changes)

    def test_live_identity_starts_pending_with_all_effects_disabled(self):
        live = TradingAccount.objects.create(
            tenant_ref="tenant-a",
            subject_ref=self.user.pk,
            account_ref="live-application-result",
            execution_mode="LIVE",
        )
        self.assertIsNone(live.paper_projection_id)
        self.assertEqual(live.status, "PENDING")
        self.assertFalse(live.trading_enabled)
        self.assertFalse(live.funding_enabled)
        self.assertFalse(live.withdrawals_enabled)
        self.assertEqual(SimulatedAccount.objects.count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TradingAccount.objects.filter(pk=live.pk).update(
                paper_projection=self.projection
            )

    def test_existing_identity_is_not_reactivated_by_account_lookup(self):
        TradingAccount.objects.filter(pk=self.account.pk).update(
            status="RESTRICTED", trading_enabled=False
        )
        identity = account_for(self.user, "tenant-a").trading_account
        self.assertEqual(identity.status, "RESTRICTED")
        self.assertFalse(identity.trading_enabled)

    def test_mismatched_projection_ownership_fails_closed(self):
        self.projection.tenant_ref = "different-tenant"
        with self.assertRaisesRegex(ValueError, "ACCOUNT_PROJECTION_MISMATCH"):
            ensure_paper_identity(self.projection)

    def test_database_prevents_mode_conversion_and_identity_reassignment(self):
        changes = (
            {"execution_mode": "LIVE", "paper_projection": None},
            {"tenant_ref": "different-tenant"},
            {"subject_ref": "different-owner"},
            {"base_currency": "EUR"},
            {"account_ref": "different-reference"},
        )
        for fields in changes:
            with self.subTest(fields=fields):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    TradingAccount.objects.filter(pk=self.account.pk).update(**fields)

    def test_database_rejects_live_creation_with_enabled_effects(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TradingAccount.objects.create(
                tenant_ref="tenant-a",
                subject_ref=self.user.pk,
                account_ref="unapproved-live",
                execution_mode="LIVE",
                status="ACTIVE",
                trading_enabled=True,
            )


class TradingAccountMigrationTests(TransactionTestCase):
    migrate_from = [("canonical_trading", "0009_merge_converged_trading_graph")]
    migrate_to = [("canonical_trading", "0011_account_identity_boundary")]

    def test_backfill_preserves_virtual_funds_and_restrictions(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        try:
            old_apps = executor.loader.project_state(self.migrate_from).apps
            Projection = old_apps.get_model("canonical_trading", "SimulatedAccount")
            projection = Projection.objects.create(
                tenant_ref="migrated-tenant",
                subject_ref="migrated-owner",
                account_ref="sim:migrated",
                status="SUSPENDED",
                quote_currency="EUR",
                total_balance=Decimal("1234.5678"),
                pending_balance=Decimal("12.50"),
            )
            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_to)
            account = TradingAccount.objects.get(pk=projection.pk)
            self.assertEqual(account.execution_mode, "PAPER")
            self.assertEqual(account.base_currency, "EUR")
            self.assertEqual(account.status, "SUSPENDED")
            self.assertFalse(account.trading_enabled)
            self.assertFalse(account.funding_enabled)
            self.assertFalse(account.withdrawals_enabled)
            self.assertEqual(
                account.paper_projection.total_balance, Decimal("1234.5678")
            )
            self.assertEqual(account.paper_projection.pending_balance, Decimal("12.50"))
            self.assertEqual(account.tenant_ref, "migrated-tenant")
            self.assertEqual(account.created_at, projection.created_at)
            MigrationExecutor(connection).migrate(self.migrate_from)
            restored = Projection.objects.get(pk=projection.pk)
            self.assertEqual(restored.total_balance, Decimal("1234.5678"))
            self.assertEqual(restored.pending_balance, Decimal("12.50"))
            self.assertEqual(restored.status, "SUSPENDED")
        finally:
            MigrationExecutor(connection).migrate(self.migrate_to)
