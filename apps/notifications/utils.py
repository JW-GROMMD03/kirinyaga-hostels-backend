from twilio.rest import Client
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def send_sms(to_number, message):
    """
    Send an SMS using Twilio.
    Returns True if successful, False otherwise.
    """
    if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_PHONE_NUMBER]):
        logger.error("Twilio credentials not configured")
        return False

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=to_number
        )
        logger.info(f"SMS sent to {to_number}")
        return True
    except Exception as e:
        logger.error(f"Twilio SMS failed: {e}")
        return False