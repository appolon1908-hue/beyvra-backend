from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from wsnotifications.service import UserNotificationService
from django.contrib.auth import get_user_model
from trade.models import Trade
from payments.models import Payment
from django.contrib.auth.signals import user_logged_in
import geoip2.database 
from users.models import UserDeviceInfo, KYC
from notifications.models import UserNotifications, Notifications
from notifications.services import emit_notification
import os

User = get_user_model()
import logging

logger = logging.getLogger(__name__)



@receiver(post_save, sender=User, dispatch_uid="send_account_creation_notification")
def send_account_creation_notification(sender, instance, created, **kwargs):
    """
    Sends a WebSocket notification when a new user account is created.
    
    """
    user_id = instance.id 
    if created:
        logger.info("User Created")
        message = {
            "title": "Account_creation",
            "body": f"Welcome, to Trade App! Your account has been created successfully.",
        }
        UserNotificationService.send_account_created(user_id, message)
        emit_notification(
            user_id=user_id,
            title="Account created",
            message="Your Beyvra account has been created successfully.",
            category="ACCOUNT_CHANGE",
        )
        
   
@receiver(post_save, sender=Trade, dispatch_uid="legacy_trade_order_placed_disabled")
def trade_order_placed(sender, instance, created, **kwargs):
    """
    Sends a WebSocket notification when a new user account is created.
    """
    user_id = instance.wallet.user.id
    if False and created:
        message = {
            "title": "Trade_order_placed",
            "body": f"Your trade order has been placed.",
        }
        UserNotificationService.trade_order_placed(user_id, message)
           
@receiver(post_save, sender=Trade, dispatch_uid="legacy_trade_execution_disabled")
def trade_execution_notification(sender, instance, **kwargs):
    user_id = instance.wallet.user.id
    if False and not instance.is_active:
        message = {
            "title": "Trade_order_executed",
            "body": f"Your trade order has been executed.",
        }
        # Trade has been executed
        logger.info(f"Trade executed: {instance}")
        UserNotificationService.trade_order_executed(user_id, message)
        
@receiver(post_save, sender=Payment)
def handling_deposit(sender, instance, **kwargs):
    user_id = instance.user.id
    if instance.status == 'Approved':
        message = {
            "title": f"{instance.type}_approved",
            "body": f"Your {instance.type} has been approved.",
        }
        UserNotificationService.handle_deposit(user_id, message)
        emit_notification(
            user_id=user_id,
            title=f"{instance.type} approved",
            message=f"Your {instance.type} has been approved.",
            category="DEPOSIT" if str(instance.type).lower() == "deposit" else "WITHDRAWAL",
            payload={"payment_id": str(instance.id), "status": instance.status},
        )
        logger.info(f" executed: {instance}")
    elif instance.status == 'Declined':
        message = {
            "title": f"{instance.type}_rejected",
            "body": f"Your {instance.type} was rejected, please try again later.",
        }
        UserNotificationService.handle_deposit(user_id, message)
        emit_notification(
            user_id=user_id,
            title=f"{instance.type} rejected",
            message=f"Your {instance.type} was rejected. Please try again later.",
            category="DEPOSIT" if str(instance.type).lower() == "deposit" else "WITHDRAWAL",
            payload={"payment_id": str(instance.id), "status": instance.status},
        )
        # Trade has been executed
       
       
@receiver(pre_save, sender=User)
def send_reset_password_notification(sender, **kwargs):
    message = {
            "title": "password_changed_confirmation",
            "body": f"Password Changed succesfully",
        }
    user = kwargs.get('instance', None)
    if user:
        user_id = user.id
        new_password = user.password
        try:
            old_password = User.objects.get(id=user.id).password
        except User.DoesNotExist:
            old_password = None
        if new_password != old_password:
            UserNotificationService.password_changed_confirmation(user_id, message)
            emit_notification(
                user_id=user_id,
                title="Password changed",
                message="Your password was changed successfully.",
                category="SECURITY",
            )
            
            

@receiver(user_logged_in)
def login_alert(sender, request, user, **kwargs):
    user_agent = (request.META.get("HTTP_USER_AGENT") or "unknown")[0:255]
    ip_address = request.META.get("REMOTE_ADDR")
    message = {
            "title": "Login_activity",
            "body": f"New Login Activity Detected from another device",
        }
    exists = UserDeviceInfo.objects.filter(ip_address=ip_address, user_agent=user_agent, user=user).exists()
    if not exists:
        UserNotificationService.handle_login_activity(user.id, message)
        emit_notification(
            user_id=user.id,
            title="New login detected",
            message="A new login to your account was detected.",
            category="SECURITY",
            payload={"ip_address": ip_address, "user_agent": user_agent},
        )
        
        
@receiver(post_save, sender=User)
def account_suspension_notification(sender, **kwargs):
    message = {
            "title": "Account_suspension",
            "body":"Your Account has been Suspended",
        }
    user = kwargs.get('instance', None)
    if not user.is_active:
        UserNotificationService.handle_account_suspension(user.id, message)
        emit_notification(
            user_id=user.id,
            title="Account suspended",
            message="Your account has been suspended.",
            category="SECURITY",
            force=True,
        )
        
        
@receiver(pre_save, sender=KYC)
def Kyc_notification_status(sender, instance,**kwargs):
    user_id = instance.user.id
    try:
        if instance.id:
            original_instance = sender.objects.get(id=instance.id)
            message = {
            "title": "KYC/AML_status_update",
            "body": f"Field KYC has changed from {original_instance.status} to {instance.status}",}
            if original_instance.status != instance.status:
                UserNotificationService.handle_kyc_notification(user_id, message)
                emit_notification(
                    user_id=user_id,
                    title="KYC status updated",
                    message=message["body"],
                    category="ACCOUNT_CHANGE",
                    payload={"status": instance.status},
                )
    except sender.DoesNotExist:
        pass
    

@receiver(pre_save, sender=Notifications)
def general_notification(sender, instance, **kwargs):
    notifications = ['Scheduled Maintenance', 'Promotional Offer']
    if instance.name in notifications:
        logger.info(instance.description)
        logger.info("True Schedule Maintenance")
        message = {
        "title": instance.name,
        "body": instance.description
        }
        logger.info(message)
        UserNotificationService.handle_general_notification(message)
        
    
