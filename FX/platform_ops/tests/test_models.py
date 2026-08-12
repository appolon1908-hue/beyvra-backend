from django.contrib.auth import get_user_model
from django.test import TestCase
from platform_ops.incidents.models import OperationalIncident
from platform_ops.incidents.services import IncidentService
from platform_ops.kill_switch.models import KillSwitch
from platform_ops.kill_switch.services import KillSwitchService
from platform_ops.release.models import ReleaseManifest

class ImmutableAndWorkflowTests(TestCase):
    def setUp(self):
        U=get_user_model();self.maker=U.objects.create_superuser(email="maker@example.test",password="x",phone_number="+15550000001");self.checker=U.objects.create_superuser(email="checker@example.test",password="x",phone_number="+15550000002")
    def test_release_manifest_is_immutable(self):
        h="a"*64;x=ReleaseManifest.objects.create(backend_sha=h,image_digests={},migration_hash=h,openapi_hash=h,sbom_hash=h,configuration_hash=h,feature_flag_policy_hash=h,test_evidence_hash=h,security_evidence_hash=h);x.state="FROZEN"
        with self.assertRaises(ValueError):x.save()
    def test_incidents_deduplicate(self):
        values={"severity":"SEV1","category":"DB","summary":"db","source":"alert","deduplication_key":"db-down"};a,created=IncidentService.open_or_get(**values);b,created2=IncidentService.open_or_get(**values);self.assertTrue(created);self.assertFalse(created2);self.assertEqual(a.id,b.id)
    def test_kill_switch_deactivation_requires_different_actor(self):
        KillSwitch.objects.update_or_create(code="GLOBAL_PLATFORM_HALT",scope_type="GLOBAL",scope_ref="",defaults={"state":"ACTIVE"});req=KillSwitchService.request_deactivation(code="GLOBAL_PLATFORM_HALT",actor=self.maker,reason_code="recovery")
        with self.assertRaises(ValueError):KillSwitchService.approve_deactivation(code="GLOBAL_PLATFORM_HALT",request_id=req.id,actor=self.maker)
        x=KillSwitchService.approve_deactivation(code="GLOBAL_PLATFORM_HALT",request_id=req.id,actor=self.checker);self.assertEqual(x.state,"INACTIVE")
