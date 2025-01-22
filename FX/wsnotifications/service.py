# notifications/admin_notifications.py
from typing import Dict, Any, Optional
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import requests

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
    def market_price_update(self, message: str, group_name: str, metadata: Optional[Dict] = None):
        """Notify user on market price updates"""
        url = 'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd'
        headers = {"accept": "application/json", 'x-cg-demo-api-key': 'CG-NgaLHLy457wk81jkXajMRGdx' }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            coins_and_prices = [
                {"name": coin["name"], "price": coin["current_price"]}
                for coin in data
            ]
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "market_prices",
                {
                    "type": "send_price_update",
                    "message": coins_and_prices
                }
            )
            return data
        else:
            print(f"Failed to fetch data: {response.status_code}")
            return None

    def trade_update(self, user):
        """Notify users about trade update"""
        return self._send_user_notification(
            message=f"New user registered: {user.email}",
            group_name = f"trade_updates{user.id}"
        )

    def price_threshold(self, event_type: str, details: Dict[str, Any]):
        pass
    def balance_changes(self, event_type: str, details: Dict[str, Any]):
        pass





