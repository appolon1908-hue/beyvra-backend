# notifications/admin_notifications.py
from typing import Dict, Any, Optional
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import requests
from users.models import User
import json
from asgiref.sync import sync_to_async
import asyncio
from notifications.models import UserAlerts
from decimal import Decimal

import logging

logger = logging.getLogger(__name__)

class AdminNotificationService:
    
    async def _send_admin_notification(self, message: str, notification_type: str, category: str):
        """Internal method to send notifications to admin group"""
        # Prepare notification payload
        payload = {
            "type": "notification_message",
            "message": {
                "message": message,
                "type": notification_type,
                "category": category,
            }
        }

        # Send to admin group via channels
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "admin_notification",
            payload
        )
        
    async def send_new_user_notification(user):
        logger.info("Sending message to Admin group")
        message = {
            "title": "Account_creation",
            "body": f"New user {user.email} just registered at {user.date_joined}",
        }
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "Admin",
            {
                "type": "send_message",
                "message": message,
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

    


class UserNotificationService:
    
    @staticmethod
    async def _send_user_notification(type, group_name, user_id=None, message=None,):
        """Internal method to send notifications to user groups"""
        # Prepare notification payload
        channel_layer = get_channel_layer()
        if channel_layer:
            try:
                # Send a message to the user's group
                await channel_layer.group_send(
                    f"{group_name}",  # Group name
                    {
                        "type": type,  # Type corresponds to a consumer method
                        "message": message,     # Actual message payload
                    }
                )
                logger.info(f"{type} message sent to user_{user_id}")
            except Exception as e:
                logger.error(f"Failed to send message to user_{user_id}: {e}")
        else:
            logger.error(f"{type}Channel layer is not configured")
            
    @staticmethod
    def sync_send_user_notification(type, group_name, user_id=None, message=None):
        """Synchronous wrapper for _send_user_notification"""
        async def wrapper():
            await UserNotificationService._send_user_notification(type, group_name, user_id, message)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(wrapper())
        finally:
            loop.close()

    
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
                UserNotificationService._send_user_notification(message=coins_and_prices, type="send_price_updates",group_name="market_prices")
                
                # try:
                #     channel_layer = get_channel_layer()
                #     async_to_sync(channel_layer.group_send)(
                #         "market_prices",
                #         {
                #             "type": "send_price_update",
                #             "message": coins_and_prices
                #         }
                #     )
                # except Exception as e:
                #     # Handle issues with channel layer
                #     logger.info(f"Error sending data to channel layer: {e}")
                #     return None
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
            UserNotificationService._send_user_notification(message=data, type="send_asset_update",group_name=f"asset_{asset_id}")
            return data
        else:
            data = response.json()
            logger.info(data)
    
    @staticmethod
    def send_account_created(user_id, message):
        UserNotificationService._send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
    
    
    @staticmethod
    def email_verification_reminder(user):
        message = {"title": "email_verification_reminder", "message": "Please verify your email to activate your account"}
        UserNotificationService._send_user_notification(user_id=user.id, message=message, type="send_message", group_name=f"user_{user.id}")
        

    @staticmethod
    def send_email_verification_message():
        channel_layer = get_channel_layer()
        message = {"title": "email_verification_reminder", "message": "Please verify your email to activate your account"}
        unverified_users = User.objects.filter(email_verified=False)
        # logger.info(unverified_users)
        for user in unverified_users:
            UserNotificationService._send_user_notification(user_id=user.id, message=message, type="send_message", group_name=f"user_{user.id}")

        
    @staticmethod
    def password_changed_confirmation(user_id, message):
        logger.info("Reached")
        UserNotificationService._send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")

    
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
        UserNotificationService._send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
            
            
    @staticmethod
    def trade_order_executed(user_id, message):
        """
        Sends a WebSocket message to the user's channel group when a trade order is executed.

        :param user_id: The ID of the user to send the message to.
        :param message: The message to be sent.
        """
        logger.info("Reached Trade Placed")
        UserNotificationService._send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
     
        
    @staticmethod
    def handle_deposit(user_id, message):
        """
        Sends a WebSocket message to the user's channel group when a deposit is approved or rejected.

        :param user_id: The ID of the user to send the message to.
        :param message: The message to be sent.
        """
        logger.info("Handling Deposit")
        UserNotificationService._send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
            
    @staticmethod
    def handle_login_activity(user_id, message):
        """
        Used to detect user activity
        """
        logger.info("Handling Login Activity")
        UserNotificationService._send_user_notification(user_id, message, type='send_message', group_name=f"user_{user_id}")
        
            
            
    @staticmethod
    def handle_account_suspension(user_id, message):
        """
        Used to send account Suspension Message
        """
        UserNotificationService._send_user_notification(user_id, message, type="send_message", user_id=f"user_{user_id}")
       
            
    @staticmethod
    def handle_kyc_notification(user_id, message):
        """
        Used to send account Suspension Message
        """
        UserNotificationService._send_user_notification(user_id, message, type="send_message", user_id=f"user_{user_id}")
            
            
    @staticmethod   
    def handle_general_notification(message):
        """
        Used to send general notification
        """
        UserNotificationService._send_user_notification(message, type="send_message", group_name="users")
            
            
    @staticmethod
    def send_price_threshold_update():
        """Celery task to send users info about their set price threshold"""
        try:
            active_alerts = UserAlerts.objects.filter(status=True)
            asset_ids = active_alerts.values_list("asset_id", flat=True).distinct()
            logger.info(active_alerts)

            # Generate URL for fetching all required asset prices
            assets_query = ",".join(asset_ids)
            logger.info(assets_query)
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={assets_query}&vs_currencies=usd"
            
            # Fetch price data
            response = UserNotificationService.make_request(url)
            data = response.json()

            # Iterate over users with active alerts
            users_with_alerts = active_alerts.values("user").distinct()
            logger.info(users_with_alerts)
            
            for user_data in users_with_alerts:
                user_id = user_data["user"]
                user = User.objects.get(id=user_id)
                user_alerts = active_alerts.filter(user=user)
                logger.info(user_alerts)

                for alert in user_alerts:
                    asset_id = alert.asset_id
                    if not asset_id or asset_id not in data:
                        continue

                    current_price = Decimal(str(data[asset_id]["usd"]))
                    logger.info(f"Current Price: {current_price}")
                    logger.info(f"Alert threshold: {alert.price_threshold}")

                    triggered = (
                        (alert.direction == "UP" and current_price >= alert.price_threshold) or
                        (alert.direction == "DOWN" and current_price <= alert.price_threshold)
                    )

                    if triggered:
                        message = {
                            "title": "price_alerts_threshold",
                            "alert_id": str(alert.id),
                            "asset_id": alert.asset_id,
                            "current_price": str(current_price),
                            "threshold_price": str(alert.price_threshold),
                            "direction": alert.direction,
                        }
                        sync_to_async(UserNotificationService._send_user_notification)(
                        group_name = "send_message"
                        message=message
                       )
        except Exception as e:
            logger.error(f"Error checking price alerts: {e}")
            raise
            
                
        
                
        
        