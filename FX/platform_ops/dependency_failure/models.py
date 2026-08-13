import uuid
from django.db import models
class DependencyFailurePolicy(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); dependency=models.CharField(max_length=80); affected_capability=models.CharField(max_length=80)
    failure_state=models.CharField(max_length=24); allowed_mode=models.CharField(max_length=24); fail_closed=models.BooleanField(default=True); fallback=models.CharField(max_length=120,blank=True)
    timeout_ms=models.PositiveIntegerField(); recovery_requirement=models.CharField(max_length=120); version=models.CharField(max_length=32)
    class Meta: unique_together=(("dependency","affected_capability","version"),)
