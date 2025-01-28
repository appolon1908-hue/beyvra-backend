# @staticmethod
#     def handle_asset_specific_sub(url, asset_id):
#         response = UserNotificationService.make_request(url)
#         if response.status_code == 200:
#             data = response.json()
#             logger.info(data)
#             UserNotificationService._send_user_notification(message=data, type="send_asset_update",group_name=f"asset_{asset_id}")
#             return data
#         else:
#             data = response.json()
#             logger.info(data)
    
#     @staticmethod
#     def send_account_created(user_id, message):
#         UserNotificationService._send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
    
    
#     @staticmethod
#     def email_verification_reminder(user):
#         message = {"title": "email_verification_reminder", "message": "Please verify your email to activate your account"}
#         UserNotificationService._send_user_notification(user_id=user.id, message=message, type="send_message", group_name=f"user_{user.id}")
        

#     @staticmethod
#     def send_email_verification_message():
#         channel_layer = get_channel_layer()
#         message = {"title": "email_verification_reminder", "message": "Please verify your email to activate your account"}
#         unverified_users = User.objects.filter(email_verified=False)
#         # logger.info(unverified_users)
#         for user in unverified_users:
#             UserNotificationService._send_user_notification(user_id=user.id, message=message, type="send_message", group_name=f"user_{user.id}")

        
#     @staticmethod
#     def password_changed_confirmation(user_id, message):
#         logger.info("Reached")
#         UserNotificationService._send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")

    
#     @staticmethod
#     def trade_order_placed(user_id, message):
#         """
#         Sends a WebSocket message to the user's channel group when a trade order is placed.

#         :param user_id: The ID of the user to send the message to.
#         :param message: The message to be sent.
#         """
#         logger.info("Reached Trade Order")
#         UserNotificationService._send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
            
            
#     @staticmethod
#     def trade_order_executed(user_id, message):
#         """
#         Sends a WebSocket message to the user's channel group when a trade order is executed.

#         :param user_id: The ID of the user to send the message to.
#         :param message: The message to be sent.
#         """
#         logger.info("Reached Trade Placed")
#         UserNotificationService._send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
     
        
#     @staticmethod
#     def handle_deposit(user_id, message):
#         """
#         Sends a WebSocket message to the user's channel group when a deposit is approved or rejected.

#         :param user_id: The ID of the user to send the message to.
#         :param message: The message to be sent.
#         """
#         logger.info("Handling Deposit")
#         UserNotificationService._send_user_notification(user_id, message, type="send_message", group_name=f"user_{user_id}")
        
            
#     @staticmethod
#     def handle_login_activity(user_id, message):
#         """
#         Used to detect user activity
#         """
#         logger.info("Handling Login Activity")
#         UserNotificationService._send_user_notification(user_id, message, type='send_message', group_name=f"user_{user_id}")
        
            
            
#     @staticmethod
#     def handle_account_suspension(user_id, message):
#         """
#         Used to send account Suspension Message
#         """
#         UserNotificationService._send_user_notification(user_id, message, type="send_message", user_id=f"user_{user_id}")
       
            
#     @staticmethod
#     def handle_kyc_notification(user_id, message):
#         """
#         Used to send account Suspension Message
#         """
#         UserNotificationService._send_user_notification(user_id, message, type="send_message", user_id=f"user_{user_id}")
            
            
#     @staticmethod   
#     def handle_general_notification(message):
#         """
#         Used to send general notification
#         """
#         UserNotificationService._send_user_notification(message, type="send_message", group_name="users")
            
            
#     @staticmethod
#     async def send_price_threshold_update():
#         """Celery task to send users info about their set price threshold"""
#         try:
#             active_alerts = UserAlerts.objects.filter(status=True)
#             asset_ids = active_alerts.values_list("asset_id", flat=True).distinct()
#             logger.info(active_alerts)

#             # Generate URL for fetching all required asset prices
#             assets_query = ",".join(asset_ids)
#             logger.info(assets_query)
#             url = f"https://api.coingecko.com/api/v3/simple/price?ids={assets_query}&vs_currencies=usd"
            
#             # Fetch price data
#             response = UserNotificationService.make_request(url)
#             data = response.json()

#             # Iterate over users with active alerts
#             users_with_alerts = active_alerts.values("user").distinct()
#             logger.info(users_with_alerts)
            
#             for user_data in users_with_alerts:
#                 user_id = user_data["user"]
#                 user = User.objects.get(id=user_id)
#                 user_alerts = active_alerts.filter(user=user)
#                 logger.info(user_alerts)

#                 for alert in user_alerts:
#                     asset_id = alert.asset_id
#                     if not asset_id or asset_id not in data:
#                         continue

#                     current_price = Decimal(str(data[asset_id]["usd"]))
#                     logger.info(f"Current Price: {current_price}")
#                     logger.info(f"Alert threshold: {alert.price_threshold}")

#                     triggered = (
#                         (alert.direction == "UP" and current_price >= alert.price_threshold) or
#                         (alert.direction == "DOWN" and current_price <= alert.price_threshold)
#                     )

#                     if triggered:
#                         message = {
#                             "title": "price_alerts_threshold",
#                             "alert_id": str(alert.id),
#                             "asset_id": alert.asset_id,
#                             "current_price": str(current_price),
#                             "threshold_price": str(alert.price_threshold),
#                             "direction": alert.direction,
#                         }
#                         await UserNotificationService._send_user_notification(
#                         group_name = "send_message",
#                         message=message
#                        )
#         except Exception as e:
#             logger.error(f"Error checking price alerts: {e}")
#             raise
            
                
        
                
        
        