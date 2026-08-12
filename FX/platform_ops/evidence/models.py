import uuid
from django.db import models
class OperationalEvidenceManifest(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); release_id=models.UUIDField(); manifest_version=models.CharField(max_length=32); candidate_hash=models.CharField(max_length=64); service_inventory_hash=models.CharField(max_length=64); config_hash=models.CharField(max_length=64); migration_hash=models.CharField(max_length=64); openapi_hash=models.CharField(max_length=64); sbom_hash=models.CharField(max_length=64); test_hash=models.CharField(max_length=64); chaos_hash=models.CharField(max_length=64); restore_hash=models.CharField(max_length=64); reconciliation_hash=models.CharField(max_length=64); created_at=models.DateTimeField(auto_now_add=True); root_hash=models.CharField(max_length=64)
    def save(self,*a,**kw):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():raise ValueError("EVIDENCE_MANIFEST_IMMUTABLE")
        return super().save(*a,**kw)
class OperationalEvidenceItem(models.Model):
    manifest=models.ForeignKey(OperationalEvidenceManifest,on_delete=models.PROTECT,related_name="items"); category=models.CharField(max_length=32); artifact_ref=models.CharField(max_length=255); sha256=models.CharField(max_length=64); created_at=models.DateTimeField(auto_now_add=True); tool_version=models.CharField(max_length=80); result=models.CharField(max_length=32)
