# notifications/admin_notifications.py
from typing import Dict, Any, Optional
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import requests
from users.models import User
import json
from asgiref.sync import sync_to_async
import asyncio
import os


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
    def _send_user_notification(user_id, message, type):
        """Internal method to send notifications to user groups"""
        # Prepare notification payload
        channel_layer = get_channel_layer()
        if channel_layer:
            try:
                # Send a message to the user's group
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",  # Group name
                    {
                        "type": "send_message",  # Type corresponds to a consumer method
                        "message": message,     # Actual message payload
                    }
                )
                logger.info(f"{type} message sent to user_{user_id}")
            except Exception as e:
                logger.error(f"Failed to send message to user_{user_id}: {e}")
        else:
            logger.error(f"{type}Channel layer is not configured")

    
    @staticmethod
    def make_request(url):
        headers = {
            "accept": "application/json",
            "x-cg-demo-api-key": os.getenv("COINGECKO_DEMO_API_KEY", "")
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
    def send_account_created(user_id, message):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {
                "type": "send_message",
                "message": message
            }
        )
    ##Used to send verify message once a user is connected
    @staticmethod
    def email_verification_reminder(user):
        message = {"title": "email_verification_reminder", "message": "Please verify your email to activate your account"}
        UserNotificationService._send_user_notification(user_id=user.id, message=message, type="Email_Verification")
        

    @staticmethod
    def send_email_verification_message():
        channel_layer = get_channel_layer()
        message = {"title": "email_verification_reminder", "message": "Please verify your email to activate your account"}
        unverified_users = User.objects.filter(email_verified=False)
        logger.info(unverified_users)
        for user in unverified_users:
            logger.info(f"user_{user.id}")
            logger.info(f"Processing user {user.id}")
            UserNotificationService._send_user_notification(user_id=user.id, message=message, type="send_email_verification_message")

        
    @staticmethod
    def password_changed_confirmation(user_id, message):
        logger.info("Reached")
        UserNotificationService._send_user_notification(user_id, message, type="Password Change")

    
    @staticmethod
    def trade_order_placed(user_id, message):
        """
        Sends a WebSocket message to the user's channel group when a trade order is placed.

        :param user_id: The ID of the user to send the message to.
        :param message: The message to be sent.
        """
        logger.info("Reached Trade Order")
        
        # Get the channel layer for WebSocket communication
        channel_layer = get_channel_layer()
        UserNotificationService._send_user_notification(user_id, message, type="Trade")
        
            
            
    @staticmethod
    def trade_order_executed(user_id, message):
        """
        Sends a WebSocket message to the user's channel group when a trade order is executed.

        :param user_id: The ID of the user to send the message to.
        :param message: The message to be sent.
        """
        logger.info("Reached Trade Placed")
        UserNotificationService._send_user_notification(user_id, message, type="Trade_Executed")
        
     
        
    @staticmethod
    def handle_deposit(user_id, message):
        """
        Sends a WebSocket message to the user's channel group when a deposit is approved or rejected.

        :param user_id: The ID of the user to send the message to.
        :param message: The message to be sent.
        """
        logger.info("Handling Deposit")
        UserNotificationService._send_user_notification(user_id, message, type="Deposit")
        
            
    @staticmethod
    def handle_login_activity(user_id, message):
        """
        Used to detect user activity
        """
        logger.info("Handling Login Activity")
        UserNotificationService._send_user_notification(user_id, message, type='Login Activity')
        
            
            
    @staticmethod
    def handle_account_suspension(user_id, message):
        """
        Used to send account Suspension Message
        """
        UserNotificationService._send_user_notification(user_id, message, type="Account Suspension")
       
            
    @staticmethod
    def handle_kyc_notification(user_id, message):
        """
        Used to send account Suspension Message
        """
        UserNotificationService._send_user_notification(user_id, message, type="KYC Notification")
            
            
    @staticmethod   
    def handle_general_notification(message):
        """
        Used to send general notification
        """
        channel_layer = get_channel_layer()
        if channel_layer:
            try:
                # Send a message to the user's group
                async_to_sync(channel_layer.group_send)(
                    f"users",  # Group name
                    {
                        "type": "send_message",  # Type corresponds to a consumer method
                        "message": message,     # Actual message payload
                    }
                )
            except Exception as e:
                pass
        else:
            logger.error(f"General Channel layer is not configured")
            
    
            
    
