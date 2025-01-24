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


async def handle_password_reset_confirmation(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "password_reset_confirmation",
        "data": event["message"]
    }))


MESSAGE_HANDLERS = {
    "Account_creation": handle_account_creation,
    "email_verification_reminder": handle_email_verification_reminder,
    "password_reset_confirmation": handle_password_reset_confirmation,
}

async def dispatch_message(consumer, event):
    """
    Dynamically dispatch messages to the appropriate handler based on the type.
    """
    message_type = event.get("message")["title"]
    logger.info(message_type)
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