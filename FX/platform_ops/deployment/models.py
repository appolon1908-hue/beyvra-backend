import uuid
from django.db import models
class DeploymentPlan(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); release_id=models.UUIDField(); environment=models.CharField(max_length=32); strategy=models.CharField(max_length=24); state=models.CharField(max_length=24,default="DRAFT"); health_gate_policy=models.JSONField(default=dict); rollback_policy=models.JSONField(default=dict); created_at=models.DateTimeField(auto_now_add=True)
