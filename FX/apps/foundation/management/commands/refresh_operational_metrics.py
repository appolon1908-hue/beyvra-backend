from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Min, Q
from django.utils import timezone
from apps.foundation.models import OutboxEvent
from apps.foundation.observability import OUTBOX_AGE, OUTBOX_PENDING, SIM_RESERVATIONS_ACTIVE, SIM_RESERVATION_AGE, set_safety_flags
from apps.trading.models import SimulatedReservation

class Command(BaseCommand):
    help="Refresh low-cardinality operational gauges from authoritative PostgreSQL state"
    def handle(self,*_args,**_options):
        pending=OutboxEvent.objects.filter(state__in=("PENDING","CLAIMED"))
        OUTBOX_PENDING.set(pending.count())
        oldest=pending.aggregate(value=Min("created_at"))["value"]
        OUTBOX_AGE.set(max(0,(timezone.now()-oldest).total_seconds()) if oldest else 0)
        active=SimulatedReservation.objects.filter(state="ACTIVE")
        SIM_RESERVATIONS_ACTIVE.set(active.count())
        reservation_oldest=active.aggregate(value=Min("created_at"))["value"]
        SIM_RESERVATION_AGE.set(max(0,(timezone.now()-reservation_oldest).total_seconds()) if reservation_oldest else 0)
        set_safety_flags(settings)
        self.stdout.write("OPERATIONAL_METRICS_REFRESHED=YES")
