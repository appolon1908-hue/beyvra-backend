import json
from django.core.management.base import BaseCommand
from apps.post_trade.reconciliation import PositionReconciler


class Command(BaseCommand):
    help = "Run read-only post-trade reconciliation and persist its evidence."
    def handle(self, *args, **options): self.stdout.write(json.dumps(PositionReconciler.run(), sort_keys=True))
