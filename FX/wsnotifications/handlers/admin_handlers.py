import json
import logging

logger = logging.getLogger(__name__)


async def admin_account_creation(consumer, event):
    await consumer.send(text_data=json.dumps({
        "type": "account_creation",
        "data": event["message"]
    }))




##Defined Notification Types
MESSAGE_HANDLERS = {
    'Account_creation': admin_account_creation
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