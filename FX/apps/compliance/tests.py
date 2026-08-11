import hashlib, hmac, json, threading, time
from django.db import close_old_connections, connection
from django.db import DatabaseError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from integrations.models import Organization, OrganizationMembership
from apps.foundation.models import OutboxEvent
from apps.foundation.publisher import envelope
from users.models import User
from .domain import AccountState, AmlState, EligibilityResult, JurisdictionState, KycState, RestrictionType, SanctionsState
from .models import ComplianceAuditEvent, ComplianceCaseEvent, ComplianceInboxEvent, ComplianceOverride, ComplianceProfile, ComplianceProviderGovernance
from .services import add_restriction, create_case, get_deposit_eligibility, get_trading_eligibility, get_transfer_eligibility, get_withdrawal_eligibility, transition_kyc, update_account_state

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
        event=OutboxEvent.objects.filter(event_type="compliance.profile.updated.v1").latest("id"); wire=envelope(event); self.assertEqual(wire["channel"],f"compliance.profile.updated.v1.{self.user.pk}"); self.assertNotIn("email",json.dumps(wire).lower())
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
    @override_settings(COMPLIANCE_WEBHOOK_SECRET="fixture-secret")
    def test_approved_callback_has_one_business_effect(self):
        user=User.objects.create_user(email="provider@example.test",phone_number="+15555550150",first_name="Provider",last_name="Fixture",password="x"); org=Organization.objects.create(name="Provider Tenant"); profile=ComplianceProfile.objects.create(user=user,organization=org,kyc_state=KycState.IN_REVIEW)
        ComplianceProviderGovernance.objects.create(provider_key="fixture",state="STAGING_APPROVED")
        body=json.dumps({"type":"verification.updated","account_ref":str(profile.pk),"result":"approved","verification_ref":"opaque-approved-fixture"}).encode(); ts=str(int(time.time())); sig=hmac.new(b"fixture-secret",ts.encode()+b"."+body,hashlib.sha256).hexdigest(); headers={"HTTP_X_COMPLIANCE_TIMESTAMP":ts,"HTTP_X_COMPLIANCE_SIGNATURE":sig,"HTTP_X_COMPLIANCE_EVENT_ID":"evt-approved"}; c=APIClient()
        self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",**headers).status_code,202); self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",**headers).json()["status"],"duplicate")
        profile.refresh_from_db(); self.assertEqual(profile.kyc_state,KycState.APPROVED); self.assertEqual(ComplianceAuditEvent.objects.filter(account=profile,event_type="KYC_STATE_CHANGED").count(),1)
    @override_settings(COMPLIANCE_WEBHOOK_SECRET="fixture-secret")
    def test_stale_callback_rejected_without_effect(self):
        ComplianceProviderGovernance.objects.create(provider_key="fixture",state="STAGING_APPROVED"); body=b"{}"; ts=str(int(time.time())-1000); sig=hmac.new(b"fixture-secret",ts.encode()+b"."+body,hashlib.sha256).hexdigest()
        response=APIClient().post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",HTTP_X_COMPLIANCE_TIMESTAMP=ts,HTTP_X_COMPLIANCE_SIGNATURE=sig,HTTP_X_COMPLIANCE_EVENT_ID="stale"); self.assertEqual(response.status_code,401); self.assertEqual(ComplianceInboxEvent.objects.count(),0)

class ComplianceAdminAuthorizationTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.create(name="Tenant A"); self.other_org=Organization.objects.create(name="Tenant B")
        self.subject=User.objects.create_user(email="subject@example.test",phone_number="+15555550200",first_name="Subject",last_name="User",password="x")
        OrganizationMembership.objects.create(user=self.subject,organization=self.org,role="member")
        self.profile=ComplianceProfile.objects.create(user=self.subject,organization=self.org,account_state=AccountState.ACTIVE,kyc_state=KycState.IN_REVIEW,aml_state=AmlState.CLEARED,sanctions_state=SanctionsState.CLEAR,jurisdiction_state=JurisdictionState.SUPPORTED)
        self.viewer=self.make_actor("viewer",201,"compliance_viewer",self.org); self.analyst=self.make_actor("analyst",202,"compliance_analyst",self.org); self.manager=self.make_actor("manager",203,"compliance_manager",self.org); self.generic_admin=self.make_actor("admin",204,"admin",self.org,is_staff=True)
        self.foreign_manager=self.make_actor("foreign",205,"compliance_manager",self.other_org)
    def make_actor(self,name,suffix,role,org,is_staff=False):
        user=User.objects.create_user(email=f"{name}@example.test",phone_number=f"+15555550{suffix}",first_name=name.title(),last_name="User",password="x",is_staff=is_staff)
        OrganizationMembership.objects.create(user=user,organization=org,role=role); return user
    def client_for(self,user): c=APIClient(); c.force_authenticate(user); return c
    def test_least_privilege_case_workflow(self):
        endpoint="/api/v1/admin/compliance/cases"; payload={"account_id":str(self.profile.pk),"case_type":"MANUAL_REVIEW","reason_codes":["MANUAL_REVIEW_REQUIRED"]}
        self.assertEqual(self.client_for(self.subject).get(endpoint).status_code,403)
        self.assertEqual(self.client_for(self.viewer).get(endpoint).status_code,200)
        self.assertEqual(self.client_for(self.viewer).post(endpoint,payload,format="json").status_code,403)
        created=self.client_for(self.analyst).post(endpoint,payload,format="json"); self.assertEqual(created.status_code,201)
        case_id=created.json()["case_id"]; self.assertEqual(self.client_for(self.analyst).post(f"{endpoint}/{case_id}/events",{"event_type":"CASE_APPROVED"},format="json").status_code,403)
        self.assertEqual(self.client_for(self.manager).post(f"{endpoint}/{case_id}/events",{"event_type":"CASE_APPROVED"},format="json").status_code,201)
        self.assertEqual(ComplianceCaseEvent.objects.filter(case_id=case_id).count(),2)
    def test_generic_admin_has_no_compliance_authority(self): self.assertEqual(self.client_for(self.generic_admin).get("/api/v1/admin/compliance/cases").status_code,403)
    def test_cross_tenant_admin_access_denied(self):
        payload={"account_id":str(self.profile.pk),"restriction_type":"TRADING_DISABLED","reason_code":"POLICY"}
        self.assertEqual(self.client_for(self.foreign_manager).post("/api/v1/admin/compliance/restrictions",payload,format="json").status_code,404)
    def test_maker_checker_override_and_audit(self):
        endpoint="/api/v1/admin/compliance/overrides"; payload={"account_id":str(self.profile.pk),"control":"KYC_STATE","new_state":"APPROVED","reason":"Verified manual fixture evidence"}
        created=self.client_for(self.analyst).post(endpoint,payload,format="json"); self.assertEqual(created.status_code,201); oid=created.json()["override_id"]
        self.assertEqual(self.client_for(self.analyst).post(f"{endpoint}/{oid}/approve",{},format="json").status_code,403)
        self.assertEqual(self.client_for(self.manager).post(f"{endpoint}/{oid}/approve",{},format="json").status_code,200)
        self.profile.refresh_from_db(); self.assertEqual(self.profile.kyc_state,KycState.APPROVED); self.assertTrue(ComplianceAuditEvent.objects.filter(account=self.profile,event_type="MANUAL_OVERRIDE").exists())
    def test_same_manager_cannot_make_and_check(self):
        payload={"account_id":str(self.profile.pk),"control":"AML_STATE","new_state":"BLOCKED","reason":"Documented synthetic risk escalation"}; c=self.client_for(self.manager); created=c.post("/api/v1/admin/compliance/overrides",payload,format="json"); oid=created.json()["override_id"]
        response=c.post(f"/api/v1/admin/compliance/overrides/{oid}/approve",{},format="json"); self.assertEqual(response.status_code,409); self.assertEqual(response.json()["error"]["code"],"MAKER_CHECKER_REQUIRED")
    def test_restriction_removal_requires_override(self):
        restriction=add_restriction(self.profile,RestrictionType.TRADING_DISABLED,"POLICY","MANUAL",self.analyst)
        payload={"account_id":str(self.profile.pk),"control":f"REMOVE_RESTRICTION:{restriction.pk}","new_state":"INACTIVE","reason":"Documented restriction removal evidence"}
        created=self.client_for(self.analyst).post("/api/v1/admin/compliance/overrides",payload,format="json"); self.client_for(self.manager).post(f"/api/v1/admin/compliance/overrides/{created.json()['override_id']}/approve",{},format="json"); restriction.refresh_from_db(); self.assertFalse(restriction.active)

class ComplianceConcurrencyTests(TransactionTestCase):
    reset_sequences=True
    def setUp(self):
        self.user=User.objects.create_user(email="concurrent@example.test",phone_number="+15555550300",first_name="Concurrent",last_name="User",password="x")
        self.actor=User.objects.create_user(email="actor@example.test",phone_number="+15555550301",first_name="Compliance",last_name="Actor",password="x")
        self.org=Organization.objects.create(name="Concurrency Tenant"); OrganizationMembership.objects.create(user=self.user,organization=self.org)
        self.profile=ComplianceProfile.objects.create(user=self.user,organization=self.org,account_state=AccountState.ACTIVE,kyc_state=KycState.IN_REVIEW,aml_state=AmlState.CLEARED,sanctions_state=SanctionsState.CLEAR,jurisdiction_state=JurisdictionState.SUPPORTED)
    def test_concurrent_callback_restriction_suspension_and_order_are_linearizable(self):
        if connection.vendor!="postgresql": self.skipTest("PostgreSQL row-lock certification")
        barrier=threading.Barrier(4); errors=[]; responses=[]
        def run(fn):
            close_old_connections(); barrier.wait()
            try:fn()
            except Exception as exc:errors.append(exc)
            finally:close_old_connections()
        def order():
            client=APIClient(); client.force_authenticate(self.user); responses.append(client.post("/api/v1/trading/orders",{"instrument":"BTCUSD","side":"BUY","order_type":"MARKET","quantity":"1"},format="json",HTTP_X_BEYVRA_SIMULATION_MODE="true",HTTP_IDEMPOTENCY_KEY="concurrent-order"))
        threads=[threading.Thread(target=run,args=(lambda:transition_kyc(self.profile.pk,KycState.APPROVED,evidence_ref="opaque-concurrent-fixture"),)),threading.Thread(target=run,args=(lambda:add_restriction(self.profile,RestrictionType.TRADING_DISABLED,"CONCURRENT_POLICY","MANUAL",self.actor),)),threading.Thread(target=run,args=(lambda:update_account_state(self.profile.pk,AccountState.SUSPENDED,actor_ref=str(self.actor.pk)),)),threading.Thread(target=run,args=(order,))]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=10)
        self.assertFalse(errors); self.assertTrue(all(not thread.is_alive() for thread in threads)); self.profile.refresh_from_db()
        self.assertEqual(self.profile.kyc_state,KycState.APPROVED); self.assertEqual(self.profile.account_state,AccountState.SUSPENDED); self.assertTrue(self.profile.restrictions.filter(active=True,restriction_type=RestrictionType.TRADING_DISABLED).exists())
        final=get_trading_eligibility(self.profile); self.assertEqual(final.result,EligibilityResult.DENIED); self.assertIn("ACCOUNT_SUSPENDED",final.reason_codes)
        self.assertEqual(len(responses),1); self.assertIn(responses[0].status_code,(201,403))

class ComplianceDatabaseIntegrityTests(TransactionTestCase):
    def setUp(self):
        self.user=User.objects.create_user(email="integrity@example.test",phone_number="+15555550350",first_name="Audit",last_name="Fixture",password="x"); self.org=Organization.objects.create(name="Integrity Tenant"); self.profile=ComplianceProfile.objects.create(user=self.user,organization=self.org)
    def test_audit_and_case_events_are_database_append_only(self):
        if connection.vendor!="postgresql":self.skipTest("PostgreSQL trigger certification")
        audit=ComplianceAuditEvent.objects.create(account=self.profile,event_type="KYC_STATE_CHANGED")
        with self.assertRaises(DatabaseError): ComplianceAuditEvent.objects.filter(pk=audit.pk).update(event_type="TAMPERED")
        case=create_case(self.profile,"MANUAL_REVIEW","NORMAL",["MANUAL_REVIEW_REQUIRED"],self.user); event=case.events.first()
        with self.assertRaises(DatabaseError): ComplianceCaseEvent.objects.filter(pk=event.pk).delete()
