import uuid
from django.db import models
class OperationalIncident(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); severity=models.CharField(max_length=8); category=models.CharField(max_length=64); state=models.CharField(max_length=32,default="OPEN"); summary=models.CharField(max_length=255); source=models.CharField(max_length=120); opened_at=models.DateTimeField(auto_now_add=True); acknowledged_at=models.DateTimeField(null=True,blank=True); resolved_at=models.DateTimeField(null=True,blank=True); owner=models.CharField(max_length=120,blank=True); release_id=models.UUIDField(null=True,blank=True); evidence_ref=models.CharField(max_length=255,blank=True); deduplication_key=models.CharField(max_length=128)
    class Meta: indexes=[models.Index(fields=["deduplication_key","state"])]
