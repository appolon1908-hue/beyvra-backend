import json
import logging

logger = logging.getLogger(__name__)


async def handle_account_creation(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "account_creation",
        "data": event["message"]
    }))

async def handle_email_verification_reminder(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "email_verification_reminder",
        "data": event["message"]
    }))


async def handle_password_changed_confirmation(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "password_reset_confirmation",
        "data": event["message"]
    }))

async def handle_trade_order_placed(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "Trade_order_placed",
        "data": event["message"]
    }))
    
async def handle_trade_order_execution(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "Trade_order_executed",
        "data": event["message"]
    }))
    
async def handle_deposit_approval(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "Deposit_approved",
        "data": event["message"]
    }))
    
async def handle_deposit_rejected(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "Deposit_rejected",
        "data": event["message"]
    }))
    
async def handle_login_activity(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "Login_activity",
        "data": event["message"]
    }))
    
async def handle_account_suspension(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "Account_suspension",
        "data": event["message"]
    }))
    
async def handle_kyc_status_update(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "KYC/AML_status_update",
        "data": event["message"]
    }))
    
async def handle_maintenance_schedule(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "Scheduled_Maintenance",
        "data": event["message"]
    }))
    
async def handle_price_threshold_update(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "Price Alerts",
        "data": event["message"]
    }))


##Defined Notification Types
MESSAGE_HANDLERS = {
    "Account_creation": handle_account_creation,
    "email_verification_reminder": handle_email_verification_reminder,
    "password_changed_confirmation": handle_password_changed_confirmation,
    "Trade_order_placed" : handle_trade_order_placed,
    "Trade_order_executed" : handle_trade_order_execution,
    "Deposit_approved": handle_deposit_approval,
    "Deposit_rejected": handle_deposit_rejected,
    "Login_activity": handle_login_activity,
    "Account_suspension": handle_account_suspension,
    "KYC/AML_status_update": handle_kyc_status_update,
    "Scheduled_Maintenance": handle_maintenance_schedule,
    "price_alerts_threshold": handle_price_threshold_update,
}

async def dispatch_message(consumer, event):
    """
    Dynamically dispatch messages to the appropriate handler based on the type.
    """
    message_type = event.get("message")["title"]
    handler = MESSAGE_HANDLERS.get(message_type)
    logger.info(handler)
    if handler:
        await handler(consumer, event)
    else:
        # Default handler or log an error if the message type is unknown
        await consumer.send(text_data=json.dumps({
            "type": "error",
            "data": f"Unknown message type: {message_type}"
        }))