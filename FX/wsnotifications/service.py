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
    async def send_user_notification(user_id, message, type, group_name):
        """Send price update for a specific asset"""
        channel_layer = get_channel_layer()
        if channel_layer:
            try:
                await channel_layer.group_send(
                    group_name,
                    {
                        "type": type,
                        "message": message
                    }
                )
                logger.info(f"{type} update sent for {user_id}")
            except Exception as e:
                logger.error(f"Failed to send {type} update for {user_id}: {e}")
            
            
    @staticmethod
    def sync_send_user_notification(user_id, message, type, group_name):
        """Synchronous wrapper for send_asset_price_update"""
        async def wrapper():
            await UserNotificationService.send_user_notification(user_id,  message, type, group_name)
        
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
                UserNotificationService.sync_send_user_notification(user_id=None, message=coins_and_prices, type="send_price_update",group_name="market_prices")
            else:
                logger.info(f"Failed to fetch data: HTTP {response.status_code} - {response.reason}")
                return None
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}")
            return None
        
        
        
    @staticmethod
    async def send_asset_price_update(asset_id, price_data):
        """Send price update for a specific asset"""
        channel_layer = get_channel_layer()
        if channel_layer:
            try:
                await channel_layer.group_send(
                    f"price_updates_{asset_id}",
                    {
                        "type": "price_update",
                        "message": {
                            "asset_id": asset_id,
                            "price": price_data
                        }
                    }
                )
                logger.info(f"Price update sent for {asset_id}")
            except Exception as e:
                logger.error(f"Failed to send price update for {asset_id}: {e}")
                
    @staticmethod
    def sync_send_asset_price_update(asset_id, price_data):
        """Synchronous wrapper for send_asset_price_update"""
        async def wrapper():
            await UserNotificationService.send_asset_price_update(asset_id, price_data)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(wrapper())
        finally:
            loop.close()
            
    @staticmethod
    def send_email_verification_message():
        message = {"title": "email_verification_reminder", "message": "Please verify your email to activate your account"}
        unverified_users = User.objects.filter(email_verified=False)
        for user in unverified_users:
            UserNotificationService.sync_send_user_notification(user_id=user.id, message=message, type="send_message", group_name=f"user_{user.id}")
        
        
    @staticmethod
    def password_changed_confirmation(user_id, message):
        logger.info("Reached")
        UserNotificationService.sync_send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
    @staticmethod
    def send_account_created(user_id, message):
        UserNotificationService.sync_send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
    
    @staticmethod
    def trade_order_placed(user_id, message):
        """
        Sends a WebSocket message to the user's channel group when a trade order is placed.

        :param user_id: The ID of the user to send the message to.
        :param message: The message to be sent.
        """
        logger.info("Reached Trade Order")
        UserNotificationService.sync_send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
    @staticmethod
    def trade_order_executed(user_id, message):
        """
        Sends a WebSocket message to the user's channel group when a trade order is executed.

        :param user_id: The ID of the user to send the message to.
        :param message: The message to be sent.
        """
        logger.info("Reached Trade Placed")
        UserNotificationService.sync_send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
    @staticmethod
    def handle_deposit(user_id, message):
        """
        Sends a WebSocket message to the user's channel group when a deposit is approved or rejected.

        :param user_id: The ID of the user to send the message to.
        :param message: The message to be sent.
        """
        logger.info("Handling Deposit")
        UserNotificationService.sync_send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
    @staticmethod
    def handle_login_activity(user_id, message):
        """
        Used to detect user activity
        """
        logger.info("Handling Login Activity")
        UserNotificationService.sync_send_user_notification(user_id, message, type='send_message', group_name=f"user_{user_id}")
        
    @staticmethod
    def handle_account_suspension(user_id, message):
        """
        Used to send account Suspension Message 
        """
        UserNotificationService.sync_send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
    
    @staticmethod
    def handle_kyc_notification(user_id, message):
        """
        Used to send account Suspension Message
        """
        UserNotificationService.sync_send_user_notification(user_id, message, type="send_message", user_id=f"user_{user_id}")
            
            
    @staticmethod   
    def handle_general_notification(message):
        """
        Used to send general notification
        """
        UserNotificationService.sync_send_user_notification(message, type="send_message", group_name="users")
        
    @staticmethod
    def send_price_threshold_update():
        
        """Celery task to send users info about their set price threshold"""
        try:
            active_alerts = UserAlerts.objects.filter(status=True)
            logger.info(active_alerts)
            # Group all asset IDs into a single batch API request
            asset_ids = ",".join(str(alert.asset_id) for alert in active_alerts)
            ##The url cant be moved to settings.py because i am accesing the asset_id from here
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={asset_ids}&vs_currencies=usd"
            response = UserNotificationService.make_request(url)
            data = response.json()
            if active_alerts:
                for user_alert in active_alerts:
                    asset_id = str(user_alert.asset_id)
                    current_price = Decimal(str(data[asset_id]["usd"]))
                    triggered = (
                        (user_alert.direction == "UP" and current_price >= user_alert.price_threshold) or
                        (user_alert.direction == "DOWN" and current_price <= user_alert.price_threshold)
                    )

                    if triggered:
                        message = {
                            "title": "price_alerts_threshold",
                            "alert_id": str(user_alert.id),
                            "asset_id": user_alert.asset_id,
                            "current_price": str(current_price),
                            "threshold_price": str(user_alert.price_threshold),
                            "direction": user_alert.direction,
                            
                        }
                        UserNotificationService.sync_send_user_notification(
                        user_id= user_alert.user.id,
                        message=message,
                        type = "send_message",
                        group_name=f"price_alerts_{user_alert.user.id}", 
                    )
            else:
                logger.info(f"No active alerts")
        except Exception as e:
            logger.error(f"Error checking price alerts: {e}")
            raise
            
            
    