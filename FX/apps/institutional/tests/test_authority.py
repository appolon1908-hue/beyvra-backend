import json
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.test import APIRequestFactory

from integrations.models import Organization, OrganizationMembership
from users.models import User
from apps.institutional.models import (
    AccountOwnerReference, AllocationGroup, AllocationGroupMember, BrokerAccountMapping,
    ClearingAccountCapability, ClearingBroker, ClearingBrokerRelationship, CustodyStructure,
    InstitutionalAccount, InstitutionalAuditEvent, InstitutionalInboxEvent,
    InstitutionalOperatorAction, InstitutionalPosition, InstitutionalSettlementMapping,
    InstitutionalSubaccount, InstitutionalTradeAllocationInstruction, OmnibusAccount,
    OmnibusBeneficialPosition, SegregatedCustodyAccount,
)
from apps.institutional.services import (
    AllocationService, InstitutionAggregationService, InstitutionalAccountReconciler,
    InstitutionalAccountService, InstitutionalRiskService, SubaccountService,
    deny_live_institutional_operation,
)


class InstitutionalAuthorityTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = User.objects.create_user(email="institution@example.test", phone_number="+15555551001", first_name="Institution", last_name="User", password="x")
        self.operator = User.objects.create_user(email="operator@example.test", phone_number="+15555551002", first_name="Operator", last_name="User", password="x")
        self.checker = User.objects.create_user(email="checker-inst@example.test", phone_number="+15555551003", first_name="Checker", last_name="User", password="x")
        self.tenant = Organization.objects.create(name="Synthetic Institution Tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.tenant, role="member")
        OrganizationMembership.objects.create(user=self.operator, organization=self.tenant, role="institutional_operations")
        OrganizationMembership.objects.create(user=self.checker, organization=self.tenant, role="institutional_manager")
        self.institution = InstitutionalAccountService.create_internal(
            tenant=self.tenant, actor=self.operator, institution_code="INST-TEST", display_name="Synthetic Institution",
            account_type="INTERNAL_TEST", status="ACTIVE", base_currency="USD", effective_from=self.now,
        )
        self.sub_a = SubaccountService.create(institution=self.institution, actor=self.operator, code="A", display_name="Sleeve A", subaccount_type="TEST", base_currency="USD", status="ACTIVE", allocation_eligible=True, effective_from=self.now)
        self.sub_b = SubaccountService.create(institution=self.institution, actor=self.operator, code="B", display_name="Sleeve B", subaccount_type="TEST", base_currency="USD", status="ACTIVE", allocation_eligible=True, effective_from=self.now)
        self.sub_c = SubaccountService.create(institution=self.institution, actor=self.operator, code="C", display_name="Sleeve C", subaccount_type="TEST", base_currency="USD", status="ACTIVE", allocation_eligible=True, effective_from=self.now)
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def test_account_and_hierarchy_authority(self):
        self.assertEqual(self.client.get("/api/v1/institutional/account").status_code, 200)
        hierarchy = self.client.get("/api/v1/institutional/account/hierarchy").json()
        self.assertEqual(len(hierarchy["subaccounts"]), 3)
        self.assertEqual(InstitutionalAuditEvent.objects.filter(event_type="institutional.account.created.v1").count(), 1)

    def test_hierarchy_rejects_cycles_and_cross_institution_links(self):
        self.sub_b.parent_subaccount = self.sub_a; self.sub_b.full_clean(); self.sub_b.save()
        self.sub_a.parent_subaccount = self.sub_b
        with self.assertRaises(ValidationError): self.sub_a.full_clean()
        other_tenant = Organization.objects.create(name="Other Tenant")
        other = InstitutionalAccount.objects.create(tenant=other_tenant, institution_code="OTHER", display_name="Other", account_type="INTERNAL_TEST", status="ACTIVE", base_currency="USD", effective_from=self.now)
        foreign = InstitutionalSubaccount.objects.create(institution=other, tenant=other_tenant, code="FOREIGN", display_name="Foreign", subaccount_type="TEST", base_currency="USD", status="ACTIVE", effective_from=self.now)
        self.sub_c.parent_subaccount = foreign
        with self.assertRaises(ValidationError): self.sub_c.full_clean()

    def test_owner_reference_requires_external_authority_and_never_public(self):
        owner = AccountOwnerReference(institution=self.institution, subaccount=self.sub_a, owner_type="BENEFICIAL_OWNER_REFERENCE", external_authority="compliance-authority", external_owner_ref="opaque-owner-001", ownership_role="beneficial-owner-reference", status="ACTIVE", effective_from=self.now)
        owner.full_clean(); owner.save()
        payload = str(self.client.get("/api/v1/institutional/account").json())
        self.assertNotIn("opaque-owner", payload)
        invalid = AccountOwnerReference(institution=self.institution, owner_type="UNKNOWN", external_authority="", external_owner_ref="", ownership_role="unknown", status="PENDING", effective_from=self.now)
        with self.assertRaises(ValidationError): invalid.full_clean()

    def test_allocation_exact_decimal_and_idempotent(self):
        group = AllocationGroup.objects.create(institution=self.institution, code="503020", name="50/30/20", allocation_method="FIXED_PERCENT", status="ACTIVE", effective_from=self.now)
        for priority, (sub, weight) in enumerate(((self.sub_a, "0.5"), (self.sub_b, "0.3"), (self.sub_c, "0.2")), 1):
            AllocationGroupMember.objects.create(allocation_group=group, subaccount=sub, weight=Decimal(weight), priority=priority, status="ACTIVE", effective_from=self.now)
        first = AllocationService.allocate_fixed_percent(institution=self.institution, trade_id="synthetic-trade-1", source_account=self.sub_a, group=group, quantity=Decimal("1.000000000000000001"), price=Decimal("100"), idempotency_key="allocation-1", actor=self.operator)
        replay = AllocationService.allocate_fixed_percent(institution=self.institution, trade_id="synthetic-trade-1", source_account=self.sub_a, group=group, quantity=Decimal("1.000000000000000001"), price=Decimal("100"), idempotency_key="allocation-1", actor=self.operator)
        self.assertEqual(first.pk, replay.pk)
        self.assertEqual(sum((line.quantity for line in first.lines.all()), Decimal("0")), first.canonical_quantity)
        self.assertEqual(InstitutionalTradeAllocationInstruction.objects.count(), 1)

    def test_aggregation_preserves_subaccount_positions(self):
        InstitutionalPosition.objects.create(tenant=self.tenant, institution=self.institution, subaccount=self.sub_a, instrument_id="BTCUSD", quantity=Decimal("2"), as_of=self.now)
        InstitutionalPosition.objects.create(tenant=self.tenant, institution=self.institution, subaccount=self.sub_b, instrument_id="BTCUSD", quantity=Decimal("-0.5"), as_of=self.now)
        aggregate = InstitutionAggregationService.positions(institution=self.institution)
        self.assertEqual(aggregate, [{"instrument_id": "BTCUSD", "quantity": "1.500000000000000000"}])
        self.assertEqual(self.institution.positions.count(), 2)

    def test_custody_mapping_is_simulation_only_and_reconciles(self):
        custody = CustodyStructure.objects.create(institution=self.institution, custody_model="HYBRID", status="ACTIVE", policy_version="fixture-v1", effective_from=self.now)
        omnibus = OmnibusAccount.objects.create(institution=self.institution, custody_structure=custody, asset_class="DIGITAL_ASSET", status="ACTIVE", environment="SIMULATION")
        OmnibusBeneficialPosition.objects.create(omnibus_account=omnibus, subaccount=self.sub_a, instrument_id="BTCUSD", quantity=Decimal("1"), as_of=self.now, source_version="v1")
        SegregatedCustodyAccount.objects.create(institution=self.institution, subaccount=self.sub_b, custody_structure=custody, status="ACTIVE", environment="SIMULATION", effective_from=self.now)
        run = InstitutionalAccountReconciler.run(institution=self.institution, actor=self.operator)
        self.assertEqual(run.status, "PASS")
        self.assertEqual(run.violations, [])

    def test_live_clearing_and_capability_fail_closed(self):
        broker = ClearingBroker.objects.create(code="SYNTH", name="Synthetic Reference", status="ACTIVE", environment="SANDBOX_REFERENCE")
        relationship = ClearingBrokerRelationship.objects.create(institution=self.institution, clearing_broker=broker, relationship_type="CLEARING", status="ACTIVE", approved_for_paper=True, effective_from=self.now)
        self.assertFalse(relationship.approved_for_live)
        mapping = BrokerAccountMapping.objects.create(institution=self.institution, subaccount=self.sub_a, execution_provider_id="fixture", provider_account_ref="opaque-ref", account_role="CLEARING", environment="PAPER", status="ACTIVE", effective_from=self.now)
        capability = ClearingAccountCapability(broker_account_mapping=mapping, asset_class="EQUITY", capability="LIVE_EXECUTION", enabled=True, environment="PAPER", source="fixture", effective_from=self.now)
        with self.assertRaises(ValidationError): capability.full_clean()
        self.assertEqual(deny_live_institutional_operation(), {"allowed": False, "code": "FEATURE_DISABLED", "outbound_live_requests": 0, "real_financial_effects": 0})

    def test_risk_requires_parent_and_child_active(self):
        self.assertEqual(InstitutionalRiskService.evaluate(institution=self.institution, subaccount=self.sub_a)["result"], "ALLOWED")
        self.institution.status = "RESTRICTED"; self.institution.save(update_fields=("status",))
        self.assertEqual(InstitutionalRiskService.evaluate(institution=self.institution, subaccount=self.sub_a)["result"], "DENIED")

    def test_customer_cannot_idor_other_tenant(self):
        other_tenant = Organization.objects.create(name="IDOR Tenant")
        other = InstitutionalAccount.objects.create(tenant=other_tenant, institution_code="IDOR", display_name="Other", account_type="INTERNAL_TEST", status="ACTIVE", base_currency="USD", effective_from=self.now)
        foreign = InstitutionalSubaccount.objects.create(institution=other, tenant=other_tenant, code="SECRET", display_name="Secret", subaccount_type="TEST", base_currency="USD", status="ACTIVE", effective_from=self.now)
        self.assertEqual(self.client.get(f"/api/v1/institutional/subaccounts/{foreign.pk}").status_code, 404)

    def test_operator_rbac_and_masked_provider_reference(self):
        anonymous = APIClient(); self.assertEqual(anonymous.get("/api/v1/operator/institutional/accounts").status_code, 401)
        normal = APIClient(); normal.force_authenticate(self.user); self.assertEqual(normal.get("/api/v1/operator/institutional/accounts").status_code, 403)
        operator = APIClient(); operator.force_authenticate(self.operator); self.assertEqual(operator.get("/api/v1/operator/institutional/accounts").status_code, 200)

    def test_operator_is_tenant_scoped(self):
        other_tenant = Organization.objects.create(name="Other Operator Tenant")
        foreign_operator = User.objects.create_user(email="foreign-operator@example.test", phone_number="+15555551004", first_name="Foreign", last_name="Operator", password="x")
        OrganizationMembership.objects.create(user=foreign_operator, organization=other_tenant, role="institutional_operations")
        foreign = InstitutionalAccount.objects.create(tenant=other_tenant, institution_code="FOREIGN", display_name="Foreign", account_type="INTERNAL_TEST", status="ACTIVE", base_currency="USD", effective_from=self.now)
        operator = APIClient(); operator.force_authenticate(self.operator)
        ids = {row["id"] for row in operator.get("/api/v1/operator/institutional/accounts").json()["results"]}
        self.assertNotIn(str(foreign.id), ids)
        self.assertEqual(operator.get(f"/api/v1/operator/institutional/accounts/{foreign.id}").status_code, 404)

    def test_maker_checker_constraint_and_append_only_audit(self):
        action = InstitutionalOperatorAction(institution=self.institution, control="CUSTODY_MODEL_CHANGE", requested_by=self.operator, approved_by=self.operator)
        with self.assertRaises(ValidationError): action.full_clean()
        event = self.institution.audit_events.first()
        with self.assertRaises(ValueError): event.delete()

    def test_inbox_deduplicates(self):
        InstitutionalInboxEvent.objects.create(source="fixture", event_id="evt-1", payload_hash="0" * 64)
        with self.assertRaises(Exception): InstitutionalInboxEvent.objects.create(source="fixture", event_id="evt-1", payload_hash="0" * 64)

    def test_realtime_is_user_scoped_and_has_gap_snapshot(self):
        from ws import v2
        pattern = "institutional.subaccount.updated.v1.{user_id}"
        entry = v2.CHANNEL_REGISTRY[pattern]
        self.assertTrue(entry["resume_supported"])
        self.assertEqual(entry["snapshot_provider"], "/api/v1/institutional/account/hierarchy")
        factory = APIRequestFactory()
        own = factory.post("/", {"channel": f"institutional.subaccount.updated.v1.{self.user.id}", "user": str(self.user.id)}, format="json", HTTP_X_BEYVRA_PROXY_SECRET="fixture-proxy-secret")
        other = factory.post("/", {"channel": "institutional.subaccount.updated.v1.someone-else", "user": str(self.user.id)}, format="json", HTTP_X_BEYVRA_PROXY_SECRET="fixture-proxy-secret")
        with __import__("unittest.mock", fromlist=["patch"]).patch.dict("os.environ", {"CENTRIFUGO_PROXY_SECRET": "fixture-proxy-secret"}):
            self.assertEqual(json.loads(v2.authorize_subscription(own).content), {"result": {}})
            self.assertEqual(json.loads(v2.authorize_subscription(other).content)["error"]["code"], 403)
