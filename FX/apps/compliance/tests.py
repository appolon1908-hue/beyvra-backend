import hashlib, hmac, json, time
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from integrations.models import Organization, OrganizationMembership
from users.models import User
from .domain import AccountState, AmlState, EligibilityResult, JurisdictionState, KycState, RestrictionType, SanctionsState
from .models import ComplianceAuditEvent, ComplianceInboxEvent, ComplianceProfile, ComplianceProviderGovernance
from .services import add_restriction, get_deposit_eligibility, get_trading_eligibility, get_transfer_eligibility, get_withdrawal_eligibility, transition_kyc

class ComplianceAuthorityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="synthetic@example.test", phone_number="+15555550101", first_name="Test", last_name="User", password="x")
        self.org = Organization.objects.create(name="Synthetic Tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.org)
        self.profile = ComplianceProfile.objects.create(user=self.user, organization=self.org)
        self.client = APIClient(); self.client.force_authenticate(self.user)
    def approve(self):
        self.profile.account_state=AccountState.ACTIVE; self.profile.kyc_state=KycState.APPROVED; self.profile.aml_state=AmlState.CLEARED; self.profile.sanctions_state=SanctionsState.CLEAR; self.profile.jurisdiction_state=JurisdictionState.SUPPORTED; self.profile.save()
    def test_defaults_fail_closed(self):
        d=get_trading_eligibility(self.profile); self.assertEqual(d.result, EligibilityResult.REVIEW_REQUIRED); self.assertIn("KYC_REQUIRED",d.reason_codes)
    def test_all_capabilities_allowed_only_when_all_authorities_clear(self):
        self.approve()
        for fn in (get_trading_eligibility,get_deposit_eligibility,get_withdrawal_eligibility,get_transfer_eligibility): self.assertEqual(fn(self.profile).result,EligibilityResult.ALLOWED)
    def test_kyc_transition_requires_evidence(self):
        transition_kyc(self.profile.pk,KycState.PENDING); transition_kyc(self.profile.pk,KycState.IN_REVIEW)
        with self.assertRaisesRegex(ValueError,"VERIFIED_EVIDENCE_REQUIRED"): transition_kyc(self.profile.pk,KycState.APPROVED)
        transition_kyc(self.profile.pk,KycState.APPROVED,evidence_ref="opaque-fixture-ref")
        self.assertEqual(ComplianceAuditEvent.objects.filter(event_type="KYC_STATE_CHANGED").count(),3)
    def test_direct_kyc_jump_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_KYC_TRANSITION"): transition_kyc(self.profile.pk,KycState.APPROVED,evidence_ref="x")
    def test_state_matrix_denies(self):
        self.approve()
        cases=(("kyc_state",KycState.PENDING,"KYC_PENDING"),("aml_state",AmlState.BLOCKED,"AML_BLOCKED"),("sanctions_state",SanctionsState.CONFIRMED_MATCH,"SANCTIONS_BLOCKED"),("jurisdiction_state",JurisdictionState.RESTRICTED,"JURISDICTION_RESTRICTED"),("account_state",AccountState.SUSPENDED,"ACCOUNT_SUSPENDED"))
        for field,value,reason in cases:
            self.approve(); setattr(self.profile,field,value); self.profile.save(); self.assertIn(reason,get_trading_eligibility(self.profile).reason_codes)
    def test_active_restriction_denies(self):
        self.approve(); add_restriction(self.profile,RestrictionType.TRADING_DISABLED,"POLICY","MANUAL",self.user); self.assertEqual(get_trading_eligibility(self.profile).result,EligibilityResult.DENIED)
    def test_profile_and_requirements_are_tenant_scoped(self):
        response=self.client.get("/api/v1/compliance/profile"); self.assertEqual(response.status_code,200); self.assertNotIn("provider_reference",response.json())
        other=User.objects.create_user(email="other@example.test",phone_number="+15555550102",first_name="Other",last_name="User",password="x"); OrganizationMembership.objects.create(user=other,organization=Organization.objects.create(name="Other")); c=APIClient(); c.force_authenticate(other); self.assertEqual(c.get("/api/v1/compliance/profile").status_code,409)
    def test_provider_session_is_not_faked(self): self.assertEqual(self.client.post("/api/v1/compliance/kyc/sessions").json()["error"]["code"],"PROVIDER_NOT_AVAILABLE")
    def test_simulation_order_gated_and_snapshotted(self):
        payload={"instrument":"BTCUSD","side":"BUY","order_type":"MARKET","quantity":"1"}; headers={"HTTP_X_BEYVRA_SIMULATION_MODE":"true","HTTP_IDEMPOTENCY_KEY":"fixture-key"}
        self.assertEqual(self.client.post("/api/v1/trading/orders",payload,format="json",**headers).status_code,403)
        self.approve(); first=self.client.post("/api/v1/trading/orders",payload,format="json",**headers); second=self.client.post("/api/v1/trading/orders",payload,format="json",**headers)
        self.assertEqual(first.status_code,201); self.assertEqual(second.status_code,200); self.assertEqual(first.json()["id"],second.json()["id"]); self.assertEqual(first.json()["eligibility_result"],"ALLOWED")
    def test_real_order_always_feature_disabled(self): self.approve(); self.assertEqual(self.client.post("/api/v1/trading/orders",{},format="json").json()["error"]["code"],"FEATURE_DISABLED")

class WebhookTests(TestCase):
    @override_settings(COMPLIANCE_WEBHOOK_SECRET="fixture-secret")
    def test_signature_timestamp_and_replay(self):
        ComplianceProviderGovernance.objects.create(provider_key="fixture",state="STAGING_APPROVED")
        body=json.dumps({"fixture":True}).encode(); ts=str(int(time.time())); sig=hmac.new(b"fixture-secret",ts.encode()+b"."+body,hashlib.sha256).hexdigest(); c=APIClient()
        headers={"HTTP_X_COMPLIANCE_TIMESTAMP":ts,"HTTP_X_COMPLIANCE_SIGNATURE":sig,"HTTP_X_COMPLIANCE_EVENT_ID":"evt-1"}
        self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",**headers).status_code,202)
        self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",**headers).json()["status"],"duplicate")
        self.assertEqual(ComplianceInboxEvent.objects.count(),1)
        headers["HTTP_X_COMPLIANCE_SIGNATURE"]="bad"; self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",**headers).status_code,401)
