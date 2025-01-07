from celery import shared_task
from .models import ManualBalanceUpdate

from .utils import send_balance_update_email


@shared_task
def async_send_balance_update_email(balance_id):
    balance = ManualBalanceUpdate.objects.get(id=balance_id)
    send_balance_update_email(balance)
