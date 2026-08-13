from django.db import transaction
from django.utils import timezone
from platform_ops.audit import record_operator_action
from .models import KillSwitch,KillSwitchDeactivationRequest
class KillSwitchService:
    @staticmethod
    @transaction.atomic
    def activate(*,code,actor,reason_code):
        switch=KillSwitch.objects.select_for_update().get(code=code,scope_type="GLOBAL",scope_ref="")
        switch.state="ACTIVE"; switch.reason_code=reason_code; switch.activated_by=actor; switch.activated_at=timezone.now(); switch.version+=1; switch.save()
        record_operator_action(actor=actor,action="kill_switch.activated",object_ref=code,reason_code=reason_code); return switch
    @staticmethod
    def request_deactivation(*,code,actor,reason_code):
        switch=KillSwitch.objects.get(code=code,scope_type="GLOBAL",scope_ref="")
        req=KillSwitchDeactivationRequest.objects.create(switch=switch,requested_by=actor,reason_code=reason_code)
        record_operator_action(actor=actor,action="kill_switch.deactivation_requested",object_ref=code,reason_code=reason_code); return req
    @staticmethod
    @transaction.atomic
    def approve_deactivation(*,code,request_id,actor):
        req=KillSwitchDeactivationRequest.objects.select_for_update().select_related("switch").get(id=request_id,switch__code=code,state="PENDING")
        if req.requested_by_id==actor.id:raise ValueError("MAKER_CHECKER_REQUIRED")
        req.state="APPROVED"; req.approved_by=actor; req.decided_at=timezone.now(); req.save()
        req.switch.state="INACTIVE"; req.switch.version+=1; req.switch.save(update_fields=["state","version"])
        record_operator_action(actor=actor,action="kill_switch.deactivated",object_ref=code,reason_code=req.reason_code); return req.switch
