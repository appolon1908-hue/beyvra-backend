# notifications/admin_notifications.py
from typing import Dict, Any, Optional
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import requests
from users.models import User
import json


import logging

logger = logging.getLogger(__name__)

class AdminNotificationService:
    def send_system_alert(self, message: str, severity: str = "WARNING", metadata: Optional[Dict] = None):
        """System alerts for critical application events"""
        return self._send_admin_notification(
            message=message,
            notification_type=severity,
            category="SYSTEM_ALERT",
        )

    def send_new_user_notification(self, user):
        
        """Notify admins about new user registrations"""
        return self._send_admin_notification(
            message=f"New user registered: {user.email}",
            notification_type="INFO",
            category="USER_MANAGEMENT",
            metadata={
                "user_id": user.id,
                "email": user.email,
                "date_joined": user.date_joined.isoformat(),
                "action_url": f"/admin/auth/user/{user.id}/change/"
            }
        )

    def send_security_alert(self, event_type: str, details: Dict[str, Any]):
        """Security-related notifications"""
        return self._send_admin_notification(
            message=f"Security alert: {event_type}",
            notification_type="ERROR",
            category="SECURITY",
            metadata={
                "event_type": event_type,
                "details": details,
                # "timestamp": timezone.now().isoformat(),
                "requires_immediate_action": True
            }
        )

    def _send_admin_notification(self, message: str, notification_type: str, category: str, metadata: Optional[Dict] = None):
        """Internal method to send notifications to admin group"""
        # Prepare notification payload
        payload = {
            "type": "notification_message",
            "message": {
                "message": message,
                "type": notification_type,
                "category": category,
                "metadata": metadata,
            }
        }

        # Send to admin group via channels
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "admin_notification",
            payload
        )


class UserNotificationService:
    
    @staticmethod
    def make_request(url):
        headers = {
            "accept": "application/json",
            "x-cg-demo-api-key": "CG-NgaLHLy457wk81jkXajMRGdx"
        }
        response = requests.get(url, headers=headers)
        return response

    @staticmethod
    def market_price_update(url):
        """Notify user on market price updates"""
        logger.info(f"Fetching market price updates from: {url}")
        response = UserNotificationService.make_request(url)
        logger.info(f"{response.status_code}")
        try:
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError as e:
                    # Handle JSON decoding error
                    logger.info(f"Error decoding JSON: {e}")
                    return None
                coins_and_prices = [
                    {"name": coin["name"], "price": coin["current_price"]}
                    for coin in data
                ]
                try:
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        "market_prices",
                        {
                            "type": "send_price_update",
                            "message": coins_and_prices
                        }
                    )
                except Exception as e:
                    # Handle issues with channel layer
                    logger.info(f"Error sending data to channel layer: {e}")
                    return None
            else:
                logger.info(f"Failed to fetch data: HTTP {response.status_code} - {response.reason}")
                return None
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}")
            return None
            
        
    @staticmethod
    def handle_asset_specific_sub(url, asset_id):
        response = UserNotificationService.make_request(url)
        if response.status_code == 200:
            data = response.json()
            logger.info(data)
            channel_layer = get_channel_layer()
            logger.info(f"asset_{asset_id}")
            async_to_sync(channel_layer.group_send)(
                f"asset_{asset_id}",
                {
                    "type": "send_asset_update",
                    "message": data
                }
            )
            return data
        else:
            data = response.json()
            logger.info(data)
    
    @staticmethod
    def send_account_created(user, message):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"users_{user.id}",
            {
                "type": "send_message",
                "message": message
            }
        )
    ##Used to send verify message once a user is connected
    @staticmethod
    async def email_verification_reminder(user):
        message = {"title": "email_verification_reminder", "message": "Please verify your email to activate your account"}
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"user_{user.id}",
            {
                "type": "send_message",
                "message": message
            }
        )
        
    @staticmethod
    def send_email_verification_message():
        message = {
        "title": "email_verification_reminder", 
        "message": "Please verify your email to activate your account"
        }
        unverified_users = User.objects.filter(email_verified=False)
        channel_layer = get_channel_layer()
        async def send_messages():
            for user in unverified_users:
                await channel_layer.group_send(
                    f"user_{user.id}",
                    {
                        'type': 'send_message',
                        'message': message
                    }
                )
    
    
    @staticmethod
    def password_reset_confirmation(user_id):
        pass
        
       
    






