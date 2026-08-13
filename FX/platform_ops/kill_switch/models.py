import uuid
from django.conf import settings
from django.db import models
class KillSwitch(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); code=models.CharField(max_length=80); scope_type=models.CharField(max_length=32,default="GLOBAL"); scope_ref=models.CharField(max_length=80,blank=True)
    state=models.CharField(max_length=16,default="INACTIVE"); reason_code=models.CharField(max_length=80,blank=True); activated_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name="activated_kill_switches")
    activated_at=models.DateTimeField(null=True,blank=True); expires_at=models.DateTimeField(null=True,blank=True); version=models.PositiveIntegerField(default=1); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: unique_together=(("code","scope_type","scope_ref"),)
class KillSwitchDeactivationRequest(models.Model):
    switch=models.ForeignKey(KillSwitch,on_delete=models.PROTECT,related_name="deactivation_requests"); requested_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="kill_switch_deactivation_requests")
    approved_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name="kill_switch_deactivation_approvals"); reason_code=models.CharField(max_length=80); state=models.CharField(max_length=16,default="PENDING"); requested_at=models.DateTimeField(auto_now_add=True); decided_at=models.DateTimeField(null=True,blank=True)
