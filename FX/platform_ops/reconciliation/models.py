import uuid
from django.db import models
class FullStackReconciliationRun(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); release_id=models.UUIDField(null=True,blank=True); state=models.CharField(max_length=24,default="RUNNING"); checks=models.JSONField(default=dict); violations=models.JSONField(default=list); started_at=models.DateTimeField(auto_now_add=True); completed_at=models.DateTimeField(null=True,blank=True); candidate_sha=models.CharField(max_length=64); policy_version=models.CharField(max_length=32)
