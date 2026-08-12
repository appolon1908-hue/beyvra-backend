from django.db import models
class FeatureFlagDefinition(models.Model):
    code=models.CharField(max_length=120,primary_key=True); owner=models.CharField(max_length=80); risk_class=models.CharField(max_length=24); default_state=models.BooleanField(default=False); fail_closed_state=models.BooleanField(default=False); expires_at=models.DateTimeField(null=True,blank=True); environment_constraints=models.JSONField(default=dict); status=models.CharField(max_length=24,default="ACTIVE"); version=models.CharField(max_length=32)
