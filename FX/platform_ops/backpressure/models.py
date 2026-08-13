import uuid
from django.db import models
class BackpressurePolicy(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); component=models.CharField(max_length=80); signal=models.CharField(max_length=80)
    warning_threshold=models.DecimalField(max_digits=20,decimal_places=4); critical_threshold=models.DecimalField(max_digits=20,decimal_places=4)
    action=models.CharField(max_length=48); recovery_threshold=models.DecimalField(max_digits=20,decimal_places=4); cooldown_seconds=models.PositiveIntegerField(default=60)
    status=models.CharField(max_length=24,default="ACTIVE"); version=models.CharField(max_length=32)
    class Meta: constraints=[models.CheckConstraint(condition=models.Q(recovery_threshold__lte=models.F("warning_threshold")) & models.Q(warning_threshold__lt=models.F("critical_threshold")),name="backpressure_threshold_order")]
