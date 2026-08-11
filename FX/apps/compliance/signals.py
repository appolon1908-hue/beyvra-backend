from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ComplianceRequirement
from .services import _enqueue

@receiver(post_save,sender=ComplianceRequirement)
def requirement_changed(sender,instance,**kwargs):
    _enqueue(instance.account,"compliance.requirement.updated.v1",{"requirement_id":str(instance.pk),"type":instance.type,"status":instance.status,"required":instance.required})
