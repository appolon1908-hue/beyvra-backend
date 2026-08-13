import uuid
from django.db import models
class ConfigurationDefinition(models.Model):
    key=models.CharField(max_length=160,primary_key=True); owner=models.CharField(max_length=80); value_type=models.CharField(max_length=24); default_safe=models.JSONField(null=True,blank=True); sensitivity=models.CharField(max_length=24); reload_behavior=models.CharField(max_length=24); required=models.BooleanField(default=False); status=models.CharField(max_length=24,default="ACTIVE"); version=models.CharField(max_length=32)
class ConfigurationSnapshot(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); release_id=models.UUIDField(); environment=models.CharField(max_length=32); config_hash=models.CharField(max_length=64); created_at=models.DateTimeField(auto_now_add=True)
