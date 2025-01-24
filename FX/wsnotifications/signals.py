from django.db.models.signals import post_save
from django.dispatch import receiver
from .service import UserNotificationService
from django.contrib.auth import get_user_model

User = get_user_model()
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=User, dispatch_uid="send_account_creation_notification")
def send_account_creation_notification(sender, instance, created, **kwargs):
    """
    Sends a WebSocket notification when a new user account is created.
    """
    logger.info("Called")
    if created:
        logger.info("User Created")
        message = {
            "title": "Account_creation",
            "body": f"Welcome, to Trade App! Your account has been created successfully.",
        }
        UserNotificationService.send_account_created(message)
        
        

        

