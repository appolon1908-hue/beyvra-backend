from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from integrations.models import Organization, OrganizationMembership
from users.models import User

from .models import (
    AccountEntitlementOverride,
    AccountPlan,
    AccountPlanAssignment,
    AccountPlanVersion,
    Entitlement,
    FeeRule,
    FeeSchedule,
    FeeWaiver,
    PlanEntitlement,
    PricingRoundingPolicy,
)
from .services import calculate_fee, market_data_access, resolve_entitlement


class PricingAuthorityTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = User.objects.create_user(
            email="pricing@example.test",
            password="safe-test-password",
        )
        self.org = Organization.objects.create(name="Pricing Fixture")
        OrganizationMembership.objects.create(user=self.user, organization=self.org)
        self.plan = AccountPlan.objects.create(
            code="FIXTURE_FREE",
            name="Fixture",
            status="ACTIVE",
            effective_from=self.now,
        )
        self.version = AccountPlanVersion.objects.create(
            plan=self.plan,
            version=1,
            status="ACTIVE",
            effective_from=self.now,
        )
        AccountPlanAssignment.objects.create(
            account=self.user,
            tenant_ref=str(self.org.id),
            plan_version=self.version,
            source="DEFAULT",
            effective_from=self.now,
        )
        self.delayed = Entitlement.objects.create(
            code="MARKET_DATA_DELAYED",
            category="MARKET_DATA",
            effective_from=self.now,
        )
        PlanEntitlement.objects.create(
            plan_version=self.version,
            entitlement=self.delayed,
            enabled=True,
        )
        self.schedule = FeeSchedule.objects.create(
            code="FIXTURE_COMMISSION",
            name="Fixture",
            fee_type="TRADING_COMMISSION",
            status="ACTIVE",
            currency="USD",
            effective_from=self.now,
        )
        self.rule = FeeRule.objects.create(
            schedule=self.schedule,
            asset_class="EQUITY",
            rate_type="BASIS_POINTS",
            rate_value=Decimal("5"),
            min_fee=Decimal("1"),
            max_fee=Decimal("10"),
            currency="USD",
            effective_from=self.now,
            rule_version=1,
        )
        PricingRoundingPolicy.objects.create(
            currency="USD",
            decimal_places=2,
            rounding_mode="HALF_UP",
            effective_from=self.now,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_plan_entitlement_and_delayed_fallback(self):
        self.assertEqual(resolve_entitlement(self.user, "MARKET_DATA_DELAYED").state, "ALLOW")
        self.assertEqual(market_data_access(self.user, "REALTIME"), "DELAYED")

    def test_global_financial_entitlements_are_denied(self):
        self.assertEqual(resolve_entitlement(self.user, "REAL_MONEY").state, "DENY")

    def test_entitlements_fail_closed_when_tenant_is_ambiguous(self):
        other_org = Organization.objects.create(name="Other Pricing Fixture")
        OrganizationMembership.objects.create(user=self.user, organization=other_org)
        AccountPlanAssignment.objects.create(
            account=self.user,
            tenant_ref=str(other_org.id),
            plan_version=self.version,
            source="DEFAULT",
            effective_from=self.now,
        )
        ambiguous = resolve_entitlement(self.user, "MARKET_DATA_DELAYED")
        selected = resolve_entitlement(
            self.user,
            "MARKET_DATA_DELAYED",
            tenant_ref=str(self.org.id),
        )
        self.assertEqual(ambiguous.effective_policy_version, "tenant-ambiguous-v1")
        self.assertEqual(selected.state, "ALLOW")

    def test_override_cannot_cross_tenant_boundaries(self):
        other_org = Organization.objects.create(name="Override Fixture")
        AccountEntitlementOverride.objects.create(
            account=self.user,
            tenant_ref=str(other_org.id),
            entitlement=self.delayed,
            override_type="DISABLE",
            reason_code="FIXTURE",
            effective_from=self.now,
            approved_by=self.user,
        )
        decision = resolve_entitlement(
            self.user,
            "MARKET_DATA_DELAYED",
            tenant_ref=str(self.org.id),
        )
        self.assertEqual(decision.state, "ALLOW")

    def test_basis_points_min_max_and_decimal(self):
        minimum = calculate_fee(
            account=self.user,
            fee_type="TRADING_COMMISSION",
            notional=Decimal("100"),
            quantity=Decimal("1"),
            asset_class="EQUITY",
        )
        maximum = calculate_fee(
            account=self.user,
            fee_type="TRADING_COMMISSION",
            notional=Decimal("100000"),
            quantity=Decimal("1"),
            asset_class="EQUITY",
        )
        self.assertEqual(minimum["amount"], Decimal("1.00"))
        self.assertEqual(maximum["amount"], Decimal("10.00"))
        with self.assertRaises(ValueError):
            calculate_fee(
                account=self.user,
                fee_type="TRADING_COMMISSION",
                notional=100.0,
                quantity=Decimal("1"),
            )

    def test_effective_dating(self):
        self.rule.effective_to = self.now - timedelta(seconds=1)
        self.rule.save()
        with self.assertRaisesRegex(ValueError, "FEE_POLICY_UNAVAILABLE"):
            calculate_fee(
                account=self.user,
                fee_type="TRADING_COMMISSION",
                notional=Decimal("1"),
                quantity=Decimal("1"),
                asset_class="EQUITY",
            )

    def test_waiver_is_explicit(self):
        FeeWaiver.objects.create(
            account=self.user,
            fee_type="TRADING_COMMISSION",
            reason="FIXTURE",
            effective_from=self.now,
            approved_by=self.user,
        )
        result = calculate_fee(
            account=self.user,
            fee_type="TRADING_COMMISSION",
            notional=Decimal("100"),
            quantity=Decimal("1"),
        )
        self.assertEqual(result["amount"], 0)

    def test_customer_apis(self):
        self.assertEqual(self.client.get("/api/v1/pricing/plan").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/entitlements").status_code, 200)
        response = self.client.post(
            "/api/v1/pricing/trading/preview",
            {"notional": "100", "quantity": "1", "asset_class": "EQUITY"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["amount"], "1.00")
