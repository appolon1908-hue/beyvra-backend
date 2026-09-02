import hashlib, hmac, json, threading, time, uuid
from datetime import timedelta
from io import StringIO
from django.db import close_old_connections, connection
from django.db import DatabaseError
from django.core.management import call_command
from django.conf import settings
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from prometheus_client import generate_latest
from integrations.models import Organization, OrganizationMembership
from apps.foundation.models import ApplicationAuditEvent, OutboxEvent
from apps.foundation.publisher import envelope
from apps.trading.models import TradingOrder
from users.models import User
from .domain import AccountState, AmlState, EligibilityResult, JurisdictionState, KycState, RestrictionType, SanctionsState
from .models import ComplianceAuditEvent, ComplianceCase, ComplianceCaseEvent, ComplianceInboxEvent, ComplianceOverride, ComplianceProfile, ComplianceProviderGovernance, ComplianceRequirement, EligibilityDecision
from .services import add_restriction, create_case, get_deposit_eligibility, get_trading_eligibility, get_transfer_eligibility, get_withdrawal_eligibility, transition_aml, transition_jurisdiction, transition_kyc, transition_sanctions, update_account_state

@override_settings(
    DEPLOYMENT_ENV="test", SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False, EXTERNAL_EXECUTION_ENABLED=False, REAL_MONEY_ENABLED=False,
)
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
        d=get_trading_eligibility(self.profile); self.assertEqual(d.result, EligibilityResult.DENIED); self.assertIn("KYC_REQUIRED",d.reason_codes)
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
            self.approve(); setattr(self.profile,field,value); self.profile.save(); decision=get_trading_eligibility(self.profile); self.assertEqual(decision.result,EligibilityResult.DENIED); self.assertIn(reason,decision.reason_codes)
    def test_review_only_authorities_return_review_required(self):
        self.approve(); self.profile.aml_state=AmlState.REVIEW_REQUIRED; self.profile.save(); self.assertEqual(get_trading_eligibility(self.profile).result,EligibilityResult.REVIEW_REQUIRED)
    def test_eligibility_refreshes_a_stale_caller_instance(self):
        self.approve(); stale=ComplianceProfile.objects.get(pk=self.profile.pk); ComplianceProfile.objects.filter(pk=self.profile.pk).update(aml_state=AmlState.BLOCKED); decision=get_trading_eligibility(stale); self.assertEqual(decision.result,EligibilityResult.DENIED); self.assertIn("AML_BLOCKED",decision.reason_codes)
    def test_active_restriction_denies(self):
        self.approve(); add_restriction(self.profile,RestrictionType.TRADING_DISABLED,"TRADING_DISABLED","MANUAL",self.user); self.assertEqual(get_trading_eligibility(self.profile).result,EligibilityResult.DENIED)
    def test_separate_authorities_require_evidence_and_audit(self):
        transition_aml(self.profile.pk,AmlState.PENDING)
        with self.assertRaisesRegex(ValueError,"VERIFIED_EVIDENCE_REQUIRED"): transition_aml(self.profile.pk,AmlState.CLEARED)
        transition_aml(self.profile.pk,AmlState.CLEARED,evidence_ref="opaque-aml-fixture")
        transition_sanctions(self.profile.pk,SanctionsState.POSSIBLE_MATCH,evidence_ref="opaque-screen-fixture")
        transition_jurisdiction(self.profile.pk,JurisdictionState.SUPPORTED,evidence_ref="opaque-profile-fixture")
        self.assertTrue(ComplianceAuditEvent.objects.filter(account=self.profile,event_type="AML_STATE_CHANGED").exists())
        self.assertTrue(ComplianceAuditEvent.objects.filter(account=self.profile,event_type="SANCTIONS_STATE_CHANGED").exists())
        self.assertTrue(ComplianceAuditEvent.objects.filter(account=self.profile,event_type="JURISDICTION_CHANGED").exists())
    def test_profile_and_requirements_are_tenant_scoped(self):
        response=self.client.get("/api/v1/compliance/profile"); self.assertEqual(response.status_code,200)
        for forbidden in ("kyc_evidence_ref","aml_evidence_ref","sanctions_evidence_ref","jurisdiction_evidence_ref"):self.assertNotIn(forbidden,response.json())
        other=User.objects.create_user(email="other@example.test",phone_number="+15555550102",first_name="Other",last_name="User",password="x"); OrganizationMembership.objects.create(user=other,organization=Organization.objects.create(name="Other")); c=APIClient(); c.force_authenticate(other); self.assertEqual(c.get("/api/v1/compliance/profile").status_code,409)
    def test_requirement_mutation_enqueues_safe_event_in_same_transaction(self):
        requirement=ComplianceRequirement.objects.create(account=self.profile,type="IDENTITY_VERIFICATION",user_action="internal-provider-note-fixture")
        events=OutboxEvent.objects.filter(event_type="compliance.requirement.updated.v1"); self.assertEqual(events.count(),1); wire=envelope(events.get()); self.assertEqual(wire["channel"],f"compliance.requirement.updated.v1.{self.user.pk}"); self.assertNotIn("email",json.dumps(wire).lower()); self.assertEqual(str(requirement.pk),wire["data"]["requirement_id"])
        payload=self.client.get("/api/v1/compliance/requirements").json(); self.assertEqual(payload["results"][0]["user_action"],"Complete identity verification."); self.assertNotIn("internal-provider-note",json.dumps(payload))
    def test_public_contracts_events_and_metrics_exclude_raw_pii(self):
        profile_payload=json.dumps(self.client.get("/api/v1/compliance/profile").json()); self.assertNotIn(self.user.email,profile_payload); self.assertNotIn(self.user.phone_number,profile_payload)
        metrics="\n".join(line for line in generate_latest().decode().splitlines() if line.startswith(("beyvra_compliance","beyvra_kyc","beyvra_aml"))); self.assertNotIn(self.user.email,metrics); self.assertNotIn(self.user.phone_number,metrics)
    def test_expiration_is_effective_immediately_in_api_and_eligibility(self):
        self.approve(); self.profile.kyc_expires_at=timezone.now()-timedelta(seconds=1); self.profile.save()
        response=self.client.get("/api/v1/compliance/profile"); self.assertEqual(response.json()["kyc_state"],KycState.EXPIRED)
        decision=get_trading_eligibility(self.profile); self.assertNotEqual(decision.result,EligibilityResult.ALLOWED); self.assertIn("KYC_REQUIRED",decision.reason_codes)
    def test_expired_manual_clearance_and_restriction_removal_fail_closed(self):
        checker=User.objects.create_user(email="checker@example.test",phone_number="+15555550109",first_name="Checker",last_name="Fixture",password="x"); self.approve(); ComplianceOverride.objects.create(account=self.profile,control="KYC_STATE",previous_state="IN_REVIEW",new_state="APPROVED",reason="Synthetic expired clearance evidence",evidence_ref="opaque-expired-fixture",requested_by=self.user,approved_by=checker,approved_at=timezone.now()-timedelta(days=2),expires_at=timezone.now()-timedelta(days=1))
        decision=get_trading_eligibility(self.profile); self.assertEqual(decision.result,EligibilityResult.DENIED); self.assertIn("KYC_REQUIRED",decision.reason_codes)
        second_user=User.objects.create_user(email="exception@example.test",phone_number="+15555550110",first_name="Exception",last_name="Fixture",password="x"); second=ComplianceProfile.objects.create(user=second_user,organization=self.org,account_state=AccountState.ACTIVE,kyc_state=KycState.APPROVED,aml_state=AmlState.CLEARED,sanctions_state=SanctionsState.CLEAR,jurisdiction_state=JurisdictionState.SUPPORTED); restriction=add_restriction(second,RestrictionType.TRADING_DISABLED,"TRADING_DISABLED","MANUAL",self.user); restriction.active=False; restriction.save(update_fields=["active"])
        ComplianceOverride.objects.create(account=second,control=f"REMOVE_RESTRICTION:{restriction.pk}",previous_state="ACTIVE",new_state="INACTIVE",reason="Synthetic expired restriction exception",requested_by=self.user,approved_by=checker,approved_at=timezone.now()-timedelta(days=2),expires_at=timezone.now()-timedelta(days=1))
        self.assertEqual(get_trading_eligibility(second).result,EligibilityResult.DENIED)
    def test_reconciliation_uses_latest_decision_and_exact_audit_link(self):
        self.approve(); get_trading_eligibility(self.profile); output=StringIO(); call_command("reconcile_compliance",stdout=output); self.assertIn("missing compliance audit events = 0",output.getvalue())
        self.profile.aml_state=AmlState.BLOCKED; self.profile.save(update_fields=["aml_state"])
        with self.assertRaises(SystemExit):call_command("reconcile_compliance",stdout=StringIO())
    def test_provider_session_is_not_faked(self): self.assertEqual(self.client.post("/api/v1/compliance/kyc/sessions").json()["error"]["code"],"PROVIDER_NOT_AVAILABLE")
    def test_simulation_order_gated_and_snapshotted(self):
        payload={"instrument":"BTCUSD","side":"BUY","order_type":"MARKET","quantity":"0.1"}; headers={"HTTP_X_BEYVRA_SIMULATION_MODE":"true","HTTP_IDEMPOTENCY_KEY":"fixture-key"}
        self.assertEqual(self.client.post("/api/v1/trading/orders",payload,format="json",**headers).status_code,403)
        self.approve(); first=self.client.post("/api/v1/trading/orders",payload,format="json",**headers); second=self.client.post("/api/v1/trading/orders",payload,format="json",**headers)
        self.assertEqual(first.status_code,201); self.assertEqual(second.status_code,200); self.assertEqual(first.json()["id"],second.json()["id"]); self.assertEqual(first.json()["eligibility_result"],"ALLOWED")
    def test_real_order_always_feature_disabled(self): self.approve(); self.assertEqual(self.client.post("/api/v1/trading/orders",{},format="json").json()["error"]["code"],"FEATURE_DISABLED")

class WebhookTests(TestCase):
    def signed_callback(self, profile, event_type, result, event_id):
        body=json.dumps({"type":event_type,"account_ref":str(profile.pk),"result":result,"verification_ref":f"opaque-{event_id}","occurred_at":timezone.now().isoformat()}).encode(); ts=str(int(time.time()))
        signature=hmac.new(b"fixture-secret",b"fixture."+ts.encode()+b"."+event_id.encode()+b"."+body,hashlib.sha256).hexdigest()
        return APIClient().post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",HTTP_X_COMPLIANCE_TIMESTAMP=ts,HTTP_X_COMPLIANCE_SIGNATURE=signature,HTTP_X_COMPLIANCE_EVENT_ID=event_id)
    @override_settings(COMPLIANCE_WEBHOOK_SECRET="fixture-secret")
    def test_signature_timestamp_and_replay(self):
        ComplianceProviderGovernance.objects.create(provider_key="fixture",state="STAGING_APPROVED")
        user=User.objects.create_user(email="replay@example.test",phone_number="+15555550149",first_name="Replay",last_name="Fixture",password="x"); profile=ComplianceProfile.objects.create(user=user,organization=Organization.objects.create(name="Replay Tenant")); body=json.dumps({"type":"verification.updated","account_ref":str(profile.pk),"result":"pending","verification_ref":"opaque-replay-fixture","occurred_at":timezone.now().isoformat()}).encode(); ts=str(int(time.time())); event_id="evt-1"; sig=hmac.new(b"fixture-secret",b"fixture."+ts.encode()+b"."+event_id.encode()+b"."+body,hashlib.sha256).hexdigest(); c=APIClient()
        headers={"HTTP_X_COMPLIANCE_TIMESTAMP":ts,"HTTP_X_COMPLIANCE_SIGNATURE":sig,"HTTP_X_COMPLIANCE_EVENT_ID":event_id}
        self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",**headers).status_code,202)
        self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",**headers).json()["status"],"duplicate")
        self.assertEqual(ComplianceInboxEvent.objects.count(),1)
        conflicting=json.dumps({"type":"verification.updated","account_ref":str(profile.pk),"result":"rejected","verification_ref":"opaque-conflict-fixture","occurred_at":timezone.now().isoformat()}).encode(); headers["HTTP_X_COMPLIANCE_SIGNATURE"]=hmac.new(b"fixture-secret",b"fixture."+ts.encode()+b"."+event_id.encode()+b"."+conflicting,hashlib.sha256).hexdigest()
        self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",conflicting,content_type="application/json",**headers).json()["error"]["code"],"WEBHOOK_REPLAY_CONFLICT")
        headers["HTTP_X_COMPLIANCE_SIGNATURE"]="bad"; self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",**headers).status_code,401)
    @override_settings(COMPLIANCE_WEBHOOK_SECRET="fixture-secret")
    def test_approved_callback_has_one_business_effect(self):
        user=User.objects.create_user(email="provider@example.test",phone_number="+15555550150",first_name="Provider",last_name="Fixture",password="x"); org=Organization.objects.create(name="Provider Tenant"); profile=ComplianceProfile.objects.create(user=user,organization=org,kyc_state=KycState.IN_REVIEW)
        ComplianceProviderGovernance.objects.create(provider_key="fixture",state="STAGING_APPROVED")
        event_id="evt-approved"; body=json.dumps({"type":"verification.updated","account_ref":str(profile.pk),"result":"approved","verification_ref":"opaque-approved-fixture","occurred_at":timezone.now().isoformat()}).encode(); ts=str(int(time.time())); sig=hmac.new(b"fixture-secret",b"fixture."+ts.encode()+b"."+event_id.encode()+b"."+body,hashlib.sha256).hexdigest(); headers={"HTTP_X_COMPLIANCE_TIMESTAMP":ts,"HTTP_X_COMPLIANCE_SIGNATURE":sig,"HTTP_X_COMPLIANCE_EVENT_ID":event_id}; c=APIClient()
        self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",**headers).status_code,202); self.assertEqual(c.post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",**headers).json()["status"],"duplicate")
        profile.refresh_from_db(); self.assertEqual(profile.kyc_state,KycState.APPROVED); self.assertEqual(ComplianceAuditEvent.objects.filter(account=profile,event_type="KYC_STATE_CHANGED").count(),1)
    @override_settings(COMPLIANCE_WEBHOOK_SECRET="fixture-secret")
    def test_stale_callback_rejected_without_effect(self):
        ComplianceProviderGovernance.objects.create(provider_key="fixture",state="STAGING_APPROVED"); body=b"{}"; ts=str(int(time.time())-1000); event_id="stale"; sig=hmac.new(b"fixture-secret",b"fixture."+ts.encode()+b"."+event_id.encode()+b"."+body,hashlib.sha256).hexdigest()
        response=APIClient().post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",HTTP_X_COMPLIANCE_TIMESTAMP=ts,HTTP_X_COMPLIANCE_SIGNATURE=sig,HTTP_X_COMPLIANCE_EVENT_ID=event_id); self.assertEqual(response.status_code,401); self.assertEqual(ComplianceInboxEvent.objects.count(),0)
    @override_settings(COMPLIANCE_WEBHOOK_SECRET="fixture-secret",COMPLIANCE_PROVIDER_RESULT_MAX_AGE_SECONDS=60)
    def test_fresh_callback_with_stale_provider_result_is_rejected(self):
        user=User.objects.create_user(email="stale-result@example.test",phone_number="+15555550151",first_name="Stale",last_name="Fixture",password="x"); org=Organization.objects.create(name="Stale Tenant"); profile=ComplianceProfile.objects.create(user=user,organization=org,kyc_state=KycState.IN_REVIEW)
        ComplianceProviderGovernance.objects.create(provider_key="fixture",state="STAGING_APPROVED"); event_id="stale-result"
        body=json.dumps({"type":"verification.updated","account_ref":str(profile.pk),"result":"approved","verification_ref":"opaque-stale-fixture","occurred_at":(timezone.now()-timedelta(minutes=2)).isoformat()}).encode(); ts=str(int(time.time())); sig=hmac.new(b"fixture-secret",b"fixture."+ts.encode()+b"."+event_id.encode()+b"."+body,hashlib.sha256).hexdigest()
        response=APIClient().post("/api/v1/compliance/webhooks/fixture",body,content_type="application/json",HTTP_X_COMPLIANCE_TIMESTAMP=ts,HTTP_X_COMPLIANCE_SIGNATURE=sig,HTTP_X_COMPLIANCE_EVENT_ID=event_id)
        self.assertEqual(response.json()["error"]["code"],"STALE_PROVIDER_RESULT"); profile.refresh_from_db(); self.assertEqual(profile.kyc_state,KycState.IN_REVIEW)
    @override_settings(COMPLIANCE_WEBHOOK_SECRET="fixture-secret")
    def test_normalized_provider_fixtures_cover_review_rejected_expired_and_possible_match(self):
        org=Organization.objects.create(name="Fixture Matrix"); ComplianceProviderGovernance.objects.create(provider_key="fixture",state="STAGING_APPROVED")
        fixtures=(("review",KycState.PENDING,"verification.updated","review","kyc_state",KycState.IN_REVIEW),("rejected",KycState.PENDING,"verification.updated","rejected","kyc_state",KycState.REJECTED),("expired",KycState.APPROVED,"verification.updated","expired","kyc_state",KycState.EXPIRED),("possible",KycState.NOT_STARTED,"sanctions.updated","possible_match","sanctions_state",SanctionsState.POSSIBLE_MATCH))
        for index,(name,kyc,event_type,result,field,expected) in enumerate(fixtures):
            user=User.objects.create_user(email=f"{name}@example.test",phone_number=f"+155555504{index:02d}",first_name="Fixture",last_name=name,password="x"); profile=ComplianceProfile.objects.create(user=user,organization=org,kyc_state=kyc)
            with self.subTest(name=name):
                self.assertEqual(self.signed_callback(profile,event_type,result,f"evt-{name}").status_code,202); profile.refresh_from_db(); self.assertEqual(getattr(profile,field),expected)

class ComplianceAdminAuthorizationTests(TestCase):
    def setUp(self):
        self.org=Organization.objects.create(name="Tenant A"); self.other_org=Organization.objects.create(name="Tenant B")
        self.subject=User.objects.create_user(email="subject@example.test",phone_number="+15555550200",first_name="Subject",last_name="User",password="x")
        OrganizationMembership.objects.create(user=self.subject,organization=self.org,role="member")
        self.profile=ComplianceProfile.objects.create(user=self.subject,organization=self.org,account_state=AccountState.ACTIVE,kyc_state=KycState.IN_REVIEW,aml_state=AmlState.CLEARED,sanctions_state=SanctionsState.CLEAR,jurisdiction_state=JurisdictionState.SUPPORTED)
        self.viewer=self.make_actor("viewer",201,"compliance_viewer",self.org); self.analyst=self.make_actor("analyst",202,"compliance_analyst",self.org); self.manager=self.make_actor("manager",203,"compliance_manager",self.org); self.generic_admin=self.make_actor("admin",204,"admin",self.org,is_staff=True); self.support=self.make_actor("support",206,"support",self.org)
        self.foreign_manager=self.make_actor("foreign",205,"compliance_manager",self.other_org)
    def make_actor(self,name,suffix,role,org,is_staff=False):
        user=User.objects.create_user(email=f"{name}@example.test",phone_number=f"+15555550{suffix}",first_name=name.title(),last_name="User",password="x",is_staff=is_staff)
        OrganizationMembership.objects.create(user=user,organization=org,role=role); return user
    def client_for(self,user): c=APIClient(); c.force_authenticate(user); return c
    def command_headers(self,version=None):
        headers={"HTTP_IDEMPOTENCY_KEY":str(uuid.uuid4()),"HTTP_X_REQUEST_ID":str(uuid.uuid4())}
        if version is not None:headers["HTTP_IF_MATCH"]=str(version)
        return headers
    def test_least_privilege_case_workflow(self):
        endpoint="/api/v1/admin/compliance/cases"; payload={"account_id":str(self.profile.pk),"case_type":"MANUAL_REVIEW","reason_codes":["MANUAL_REVIEW_REQUIRED"]}
        self.assertEqual(self.client_for(self.subject).get(endpoint).status_code,403)
        self.assertEqual(self.client_for(self.viewer).get(endpoint).status_code,200)
        self.assertEqual(self.client_for(self.viewer).post(endpoint,payload,format="json").status_code,403)
        created=self.client_for(self.analyst).post(endpoint,payload,format="json",**self.command_headers()); self.assertEqual(created.status_code,201)
        case_id=created.json()["case_id"]
        assigned=self.client_for(self.analyst).post(f"{endpoint}/{case_id}/events",{"event_type":"CASE_ASSIGNED","metadata":{"assigned_to_id":str(self.analyst.pk),"unsafe_note":"must not persist"}},format="json",**self.command_headers(created.json()["version"])); self.assertEqual(assigned.status_code,201)
        case=ComplianceCaseEvent.objects.get(pk=assigned.json()["event_id"]).case; self.assertEqual(case.assigned_to,self.analyst); self.assertNotIn("unsafe_note",case.events.get(pk=assigned.json()["event_id"]).metadata)
        note=self.client_for(self.analyst).post(f"{endpoint}/{case_id}/events",{"event_type":"CASE_NOTE_ADDED","metadata":{"note_ref":"opaque-note-evidence"}},format="json",**self.command_headers(assigned.json()["case_version"])); self.assertEqual(note.status_code,201)
        self.assertNotEqual(note.json()["case_version"],assigned.json()["case_version"])
        self.assertTrue({"idempotency-key","x-request-id","if-match"}.issubset(settings.CORS_ALLOW_HEADERS))
        self.assertEqual(self.client_for(self.analyst).post(f"{endpoint}/{case_id}/events",{"event_type":"CASE_APPROVED"},format="json").status_code,403)
        self.assertEqual(self.client_for(self.manager).post(f"{endpoint}/{case_id}/events",{"event_type":"CASE_APPROVED"},format="json",**self.command_headers(note.json()["case_version"])).status_code,201)
        self.assertEqual(ComplianceCaseEvent.objects.filter(case_id=case_id).count(),4)
    def test_generic_admin_and_support_have_no_compliance_authority(self):
        self.assertEqual(self.client_for(self.generic_admin).get("/api/v1/admin/compliance/cases").status_code,403); self.assertEqual(self.client_for(self.support).get("/api/v1/admin/compliance/cases").status_code,403)
    def test_cross_tenant_admin_access_denied(self):
        payload={"account_id":str(self.profile.pk),"restriction_type":"TRADING_DISABLED","reason_code":"TRADING_DISABLED"}
        self.assertEqual(self.client_for(self.foreign_manager).post("/api/v1/admin/compliance/restrictions",payload,format="json").status_code,404)
    def test_maker_checker_override_and_audit(self):
        endpoint="/api/v1/admin/compliance/overrides"; payload={"account_id":str(self.profile.pk),"control":"KYC_STATE","new_state":"APPROVED","reason":"Verified manual fixture evidence","evidence_ref":"opaque-manual-evidence-fixture"}
        without_evidence={key:value for key,value in payload.items() if key!="evidence_ref"}; self.assertEqual(self.client_for(self.analyst).post(endpoint,without_evidence,format="json",**self.command_headers(self.profile.version)).json()["error"]["code"],"VERIFIED_EVIDENCE_REQUIRED")
        created=self.client_for(self.analyst).post(endpoint,payload,format="json",**self.command_headers(self.profile.version)); self.assertEqual(created.status_code,201); oid=created.json()["override_id"]
        self.assertEqual(self.client_for(self.analyst).post(f"{endpoint}/{oid}/approve",{},format="json").status_code,403)
        self.assertEqual(self.client_for(self.manager).post(f"{endpoint}/{oid}/approve",{},format="json",**self.command_headers(created.json()["version"])).status_code,200)
        self.profile.refresh_from_db(); self.assertEqual(self.profile.kyc_state,KycState.APPROVED); self.assertTrue(ComplianceAuditEvent.objects.filter(account=self.profile,event_type="MANUAL_OVERRIDE").exists()); self.assertTrue(ComplianceAuditEvent.objects.filter(account=self.profile,event_type="KYC_STATE_CHANGED").exists())
    def test_same_manager_cannot_make_and_check(self):
        payload={"account_id":str(self.profile.pk),"control":"AML_STATE","new_state":"BLOCKED","reason":"Documented synthetic risk escalation"}; c=self.client_for(self.manager); created=c.post("/api/v1/admin/compliance/overrides",payload,format="json",**self.command_headers(self.profile.version)); oid=created.json()["override_id"]
        response=c.post(f"/api/v1/admin/compliance/overrides/{oid}/approve",{},format="json",**self.command_headers(created.json()["version"])); self.assertEqual(response.status_code,409); self.assertEqual(response.json()["error"]["code"],"MAKER_CHECKER_REQUIRED")
    def test_restriction_removal_requires_override(self):
        restriction=add_restriction(self.profile,RestrictionType.TRADING_DISABLED,"TRADING_DISABLED","MANUAL",self.analyst)
        payload={"account_id":str(self.profile.pk),"control":f"REMOVE_RESTRICTION:{restriction.pk}","new_state":"INACTIVE","reason":"Documented restriction removal evidence"}
        self.profile.refresh_from_db(); created=self.client_for(self.analyst).post("/api/v1/admin/compliance/overrides",payload,format="json",**self.command_headers(self.profile.version)); self.client_for(self.manager).post(f"/api/v1/admin/compliance/overrides/{created.json()['override_id']}/approve",{},format="json",**self.command_headers(created.json()["version"])); restriction.refresh_from_db(); self.assertFalse(restriction.active)

    def test_case_command_replays_once_and_rejects_semantic_key_reuse(self):
        endpoint="/api/v1/admin/compliance/cases"; payload={"account_id":str(self.profile.pk),"case_type":"MANUAL_REVIEW","reason_codes":["MANUAL_REVIEW_REQUIRED"]}
        headers={"HTTP_IDEMPOTENCY_KEY":"case-replay","HTTP_X_REQUEST_ID":"case-request"}; client=self.client_for(self.analyst)
        first=client.post(endpoint,payload,format="json",**headers); replay=client.post(endpoint,payload,format="json",**headers)
        self.assertEqual((first.status_code,replay.status_code),(201,201)); self.assertEqual(first.json(),replay.json()); self.assertEqual(ComplianceCase.objects.count(),1); self.assertEqual(ApplicationAuditEvent.objects.filter(action="compliance.case.created").count(),1)
        conflict=client.post(endpoint,{**payload,"priority":"HIGH"},format="json",**headers)
        self.assertEqual(conflict.status_code,409); self.assertEqual(conflict.json()["error"]["code"],"IDEMPOTENCY_CONFLICT")

    def test_restriction_command_rejects_stale_version_and_replays_once(self):
        endpoint="/api/v1/admin/compliance/restrictions"; payload={"account_id":str(self.profile.pk),"restriction_type":"TRADING_DISABLED","reason_code":"TRADING_DISABLED"}; client=self.client_for(self.analyst)
        stale=client.post(endpoint,payload,format="json",HTTP_IDEMPOTENCY_KEY="stale-restriction",HTTP_IF_MATCH="999",HTTP_X_REQUEST_ID="stale-request")
        self.assertEqual(stale.status_code,409); self.assertFalse(self.profile.restrictions.exists())
        headers={"HTTP_IDEMPOTENCY_KEY":"restriction-replay","HTTP_IF_MATCH":str(self.profile.version),"HTTP_X_REQUEST_ID":"restriction-request"}
        first=client.post(endpoint,payload,format="json",**headers); replay=client.post(endpoint,payload,format="json",**headers)
        self.assertEqual((first.status_code,replay.status_code),(201,201)); self.assertEqual(first.json(),replay.json()); self.assertEqual(self.profile.restrictions.count(),1)

    def test_override_approval_replay_has_one_immutable_effect(self):
        payload={"account_id":str(self.profile.pk),"control":"AML_STATE","new_state":"BLOCKED","reason":"Documented synthetic risk escalation"}
        created=self.client_for(self.analyst).post("/api/v1/admin/compliance/overrides",payload,format="json",HTTP_IDEMPOTENCY_KEY="override-create",HTTP_IF_MATCH=str(self.profile.version),HTTP_X_REQUEST_ID="override-create-request")
        endpoint=f"/api/v1/admin/compliance/overrides/{created.json()['override_id']}/approve"; headers={"HTTP_IDEMPOTENCY_KEY":"override-approve","HTTP_IF_MATCH":created.json()["version"],"HTTP_X_REQUEST_ID":"override-approve-request"}; manager=self.client_for(self.manager)
        first=manager.post(endpoint,{},format="json",**headers); replay=manager.post(endpoint,{},format="json",**headers)
        self.assertEqual((first.status_code,replay.status_code),(200,200)); self.assertEqual(first.json(),replay.json()); self.assertEqual(ComplianceAuditEvent.objects.filter(account=self.profile,event_type="MANUAL_OVERRIDE").count(),1); self.assertEqual(ApplicationAuditEvent.objects.filter(action="compliance.override.approved",request_id="override-approve-request").count(),1)
        second_key=manager.post(endpoint,{},format="json",HTTP_IDEMPOTENCY_KEY="override-second-key",HTTP_IF_MATCH=created.json()["version"],HTTP_X_REQUEST_ID="override-second-request")
        self.assertEqual(second_key.status_code,409); self.assertEqual(second_key.json()["error"]["code"],"OVERRIDE_ALREADY_APPROVED")
        self.assertEqual(ApplicationAuditEvent.objects.filter(action="compliance.override.approved").count(),1)

@override_settings(
    SIMULATED_TRADING_ENABLED=True,
    REAL_TRADING_ENABLED=False,
    EXTERNAL_EXECUTION_ENABLED=False,
    REAL_MONEY_ENABLED=False,
)
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
        threads=[threading.Thread(target=run,args=(lambda:transition_kyc(self.profile.pk,KycState.APPROVED,evidence_ref="opaque-concurrent-fixture"),)),threading.Thread(target=run,args=(lambda:add_restriction(self.profile,RestrictionType.TRADING_DISABLED,"TRADING_DISABLED","MANUAL",self.actor),)),threading.Thread(target=run,args=(lambda:update_account_state(self.profile.pk,AccountState.SUSPENDED,actor_ref=str(self.actor.pk)),)),threading.Thread(target=run,args=(order,))]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=10)
        self.assertFalse(errors); self.assertTrue(all(not thread.is_alive() for thread in threads)); self.profile.refresh_from_db()
        self.assertEqual(self.profile.kyc_state,KycState.APPROVED); self.assertEqual(self.profile.account_state,AccountState.SUSPENDED); self.assertTrue(self.profile.restrictions.filter(active=True,restriction_type=RestrictionType.TRADING_DISABLED).exists())
        final=get_trading_eligibility(self.profile); self.assertEqual(final.result,EligibilityResult.DENIED); self.assertIn("ACCOUNT_SUSPENDED",final.reason_codes)
        self.assertEqual(len(responses),1); self.assertIn(responses[0].status_code,(201,403)); self.assertFalse(TradingOrder.objects.filter(account_ref=str(self.profile.pk),state="PENDING").exists())
        if responses[0].status_code==201:self.assertEqual(TradingOrder.objects.get(pk=responses[0].json()["id"]).state,"REJECTED")

class ComplianceDatabaseIntegrityTests(TransactionTestCase):
    def setUp(self):
        self.user=User.objects.create_user(email="integrity@example.test",phone_number="+15555550350",first_name="Audit",last_name="Fixture",password="x"); self.org=Organization.objects.create(name="Integrity Tenant"); self.profile=ComplianceProfile.objects.create(user=self.user,organization=self.org)
    def test_audit_and_case_events_are_database_append_only(self):
        if connection.vendor!="postgresql":self.skipTest("PostgreSQL trigger certification")
        audit=ComplianceAuditEvent.objects.create(account=self.profile,event_type="KYC_STATE_CHANGED")
        with self.assertRaises(DatabaseError): ComplianceAuditEvent.objects.filter(pk=audit.pk).update(event_type="TAMPERED")
        case=create_case(self.profile,"MANUAL_REVIEW","NORMAL",["MANUAL_REVIEW_REQUIRED"],self.user); event=case.events.first()
        with self.assertRaises(DatabaseError): ComplianceCaseEvent.objects.filter(pk=event.pk).delete()
        decision=EligibilityDecision.objects.create(account=self.profile,capability="TRADING",result="DENIED",reason_codes=["KYC_REQUIRED"],policy_version="fixture",evaluated_at=timezone.now())
        with self.assertRaises(DatabaseError): EligibilityDecision.objects.filter(pk=decision.pk).update(result="ALLOWED")
    def test_profile_deletion_requires_retention_review(self):
        if connection.vendor!="postgresql":self.skipTest("PostgreSQL retention trigger certification")
        with self.assertRaises(DatabaseError): ComplianceProfile.objects.filter(pk=self.profile.pk).delete()
        override=ComplianceOverride.objects.create(account=self.profile,control="AML_STATE",previous_state="NOT_SCREENED",new_state="BLOCKED",reason="Synthetic retained override evidence",requested_by=self.user)
        with self.assertRaises(DatabaseError): ComplianceOverride.objects.filter(pk=override.pk).delete()
    def test_database_rejects_noncanonical_authority_state(self):
        if connection.vendor!="postgresql":self.skipTest("PostgreSQL state constraint certification")
        with self.assertRaises(DatabaseError): ComplianceProfile.objects.filter(pk=self.profile.pk).update(kyc_state="VERIFIED")
        with self.assertRaises(DatabaseError): ComplianceOverride.objects.create(account=self.profile,control="AML_STATE",previous_state="NOT_SCREENED",new_state="BLOCKED",reason="Synthetic invalid self approval",requested_by=self.user,approved_by=self.user,approved_at=timezone.now())
        with self.assertRaises(DatabaseError): ComplianceOverride.objects.create(account=self.profile,control="KYC_STATE",previous_state="IN_REVIEW",new_state="APPROVED",reason="Synthetic missing evidence",requested_by=self.user)
