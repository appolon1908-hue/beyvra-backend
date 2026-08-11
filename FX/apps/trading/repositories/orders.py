from django.db import transaction

from apps.trading.domain.orders import transition_order
from apps.trading.models import TradingOrder


@transaction.atomic
def transition_persisted_order(order_id, target_state):
    order = TradingOrder.objects.select_for_update().get(pk=order_id)
    order.state = transition_order(order.state, target_state).value
    order.save(update_fields=("state", "updated_at"))
    return order
