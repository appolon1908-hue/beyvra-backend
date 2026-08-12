import uuid
from django.db import models
class BackupManifest(models.Model):
    backup_id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); database_version=models.CharField(max_length=32); release_id=models.UUIDField(); started_at=models.DateTimeField(); completed_at=models.DateTimeField(null=True,blank=True); size=models.PositiveBigIntegerField(default=0); sha256=models.CharField(max_length=64); encryption_state=models.CharField(max_length=24); storage_state=models.CharField(max_length=24); verification_state=models.CharField(max_length=24,default="PENDING")
