import uuid
from django.db import models

class CapacityProfile(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    service_code=models.CharField(max_length=80); resource_type=models.CharField(max_length=64); environment=models.CharField(max_length=24)
    tested_limit=models.DecimalField(max_digits=20,decimal_places=4); safe_operating_limit=models.DecimalField(max_digits=20,decimal_places=4)
    unit=models.CharField(max_length=32); safety_factor=models.DecimalField(max_digits=5,decimal_places=4,default="0.7000")
    test_sha=models.CharField(max_length=64); tested_at=models.DateTimeField(); evidence_ref=models.CharField(max_length=255); status=models.CharField(max_length=24,default="CERTIFIED")
    class Meta: constraints=[models.CheckConstraint(condition=models.Q(safe_operating_limit__lte=models.F("tested_limit")),name="capacity_safe_lte_tested")]
