from django.db import models
class OperationalModeState(models.Model):
    mode=models.CharField(max_length=24); reason_code=models.CharField(max_length=64); source=models.CharField(max_length=64); observed_at=models.DateTimeField(auto_now_add=True)
