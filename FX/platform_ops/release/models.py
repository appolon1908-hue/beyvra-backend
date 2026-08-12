import uuid
from django.db import models
class ReleaseManifest(models.Model):
    release_id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); backend_sha=models.CharField(max_length=64); frontend_sha=models.CharField(max_length=64,blank=True); financial_service_sha=models.CharField(max_length=64,blank=True)
    image_digests=models.JSONField(default=dict); migration_hash=models.CharField(max_length=64); openapi_hash=models.CharField(max_length=64); sbom_hash=models.CharField(max_length=64); configuration_hash=models.CharField(max_length=64); feature_flag_policy_hash=models.CharField(max_length=64); test_evidence_hash=models.CharField(max_length=64); security_evidence_hash=models.CharField(max_length=64)
    created_at=models.DateTimeField(auto_now_add=True); state=models.CharField(max_length=32,default="DRAFT")
    def save(self,*a,**kw):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():raise ValueError("RELEASE_MANIFEST_IMMUTABLE")
        return super().save(*a,**kw)
