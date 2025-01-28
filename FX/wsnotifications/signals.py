from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from wsnotifications.service import UserNotificationService, AdminNotificationService
from django.contrib.auth import get_user_model
from trade.models import Trade
from payments.models import Payment
from django.contrib.auth.signals import user_logged_in
import geoip2.database 
from users.models import UserDeviceInfo, KYC
from notifications.models import UserNotifications, Notifications
import os
from asgiref.sync import async_to_sync

import logging


User = get_user_model()
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
        async_to_sync(UserNotificationService.send_account_created)(user_id, message)
        async_to_sync(AdminNotificationService.send_new_user_notification)(instance)
        

@receiver(pre_save, sender=User)
def send_account_verification_message(sender, instance, **kwargs):
    if instance.email_verified == True:
        AdminNotificationService.send_account_verification(user=instance)
        
        
    
    
        
        
   
@receiver(post_save, sender=Trade, dispatch_uid="trade_order_placed")
def trade_order_placed(sender, instance, created, **kwargs):
    """
    Sends a WebSocket notification when a new user account is created.
    """
    user_id = instance.wallet.user.id
    if created:
        message = {
            "title": "Trade_order_placed",
            "body": f"Your trade order has been placed.",
        }
        UserNotificationService.trade_order_placed(user_id, message)
           
@receiver(post_save, sender=Trade)
def trade_execution_notification(sender, instance, **kwargs):
    user_id = instance.wallet.user.id
    if not instance.is_active:
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
        logger.info(f" executed: {instance}")
    elif instance.status == 'Declined':
        message = {
            "title": f"{instance.type}_rejected",
            "body": f"Your {instance.type} was rejected, please try again later.",
        }
        UserNotificationService.handle_deposit(user_id, message)
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
            
            

@receiver(user_logged_in)
def login_alert(sender, request, user, **kwargs):
    user_agent = request.META.get("HTTP_USER_AGENT")[0:255]
    ip_address = request.META.get("REMOTE_ADDR")
    message = {
            "title": "Login_activity",
            "body": f"New Login Activity Detected from another device",
        }
    exists = UserDeviceInfo.objects.filter(ip_address=ip_address, user_agent=user_agent, user=user).exists()
    logger.info(exists)
    if exists==False:
        UserNotificationService.handle_login_activity(user.id, message)
        
        
@receiver(post_save, sender=User)
def account_suspension_notification(sender, **kwargs):
    message = {
            "title": "Account_suspension",
            "body":"Your Account has been Suspended",
        }
    user = kwargs.get('instance', None)
    if not user.is_active:
        UserNotificationService.handle_account_suspension(user.id, message)
        
        
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
        
    
