import requests
import time
import os
from django.core.cache import cache
from django.conf import settings
from decimal import Decimal
from django import template
from django.core.mail import EmailMultiAlternatives
import logging

logger = logging.getLogger(__name__)

class ExchangeRateService:
    def __init__(self):
        self.api_key = getattr(settings, "FIXER_API_KEY", "")
        self.api_url = 'https://data.fixer.io/api/latest'
        self.cache_timeout = 3600  # Cache exchange rates for 1 hour

    def get_rate(self, base_currency, target_currency):
        """
        Get the exchange rate from base_currency to target_currency.
        Handles retries, fallback to cache, and unsupported pairs.
        """
        if base_currency == target_currency:
            return Decimal(1)  # No conversion needed

        cache_key = f"exchange_rate_{base_currency}_{target_currency}"
        cached_rate = cache.get(cache_key)

        if cached_rate:
            logger.info(f"Using cached exchange rate for {base_currency} to {target_currency}: {cached_rate}")
            return cached_rate

        retries = 3
        while retries > 0:
            try:
                response = requests.get(
                    self.api_url,
                    params={"access_key": self.api_key, "base": str(base_currency), "symbols": str(target_currency)},
                    timeout=10,
                )
                data = response.json()

                if response.status_code == 200 and 'rates' in data and target_currency in data['rates']:
                    rate = Decimal(data['rates'][target_currency])
                    cache.set(cache_key, rate, self.cache_timeout)
                    return rate
                else:
                    logger.error(f"Unsupported currency pair: {base_currency} to {target_currency}")
                    return None
            except requests.exceptions.RequestException as e:
                logger.error(f"API request failed: {e}")
                time.sleep(2)  # Wait before retrying
                retries -= 1

        # If all retries fail, fallback to cached rate if available
        if cached_rate:
            logger.warning(f"Falling back to cached rate for {base_currency} to {target_currency}: {cached_rate}")
            return cached_rate

        logger.error(f"Failed to retrieve exchange rate for {base_currency} to {target_currency}")
        return None

    

def send_balance_update_email(balance):
    """ 
    Send an email to the user when their wallet balance is updated by an admin manually.
     
    Args:
        balance (ManualBalanceUpdate): The balance object that was updated.
    """
    
    subject = "Balance Update Notification | Tradx.io"
    email_template = template.loader.get_template("email_balance_update.html")

    context = {
        "user": balance.wallet.user.first_name or balance.wallet.user.email,
        "email": balance.wallet.user.email,
        "wallet": balance.wallet.name,
        "new_balance": balance.new_balance,
        "previous_balance": balance.previous_balance,
        "reason": balance.reason,
        "description": balance.description,
        "admin": balance.admin.first_name or balance.admin.email,
        "created_at": balance.created_at,
        "frontend_url": os.getenv("FRONTEND_URL"),
    }

    html_content = email_template.render(context)
    text_content = " "
    msg = EmailMultiAlternatives(subject, text_content, settings.EMAIL_HOST_USER, [context['email']])
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)
