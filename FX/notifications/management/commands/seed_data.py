from django.core.management.base import BaseCommand
from notifications.models import Notifications


class Command(BaseCommand):
    help = "Seeds the database with initial data"

    def handle(self, *args, **kwargs):
        # Define the initial data
        notifications_data = [
            {"name": "Promos", "description": "Special offers, news and features"},
            {"name": "Trading", "description": "Trade results and price alerts"},
            {"name": "Trading Signal", "description": "Only for intraday and Swing signals categories"},
            {"name": "Push Notifications", "description": "Receive push notifications directly in your browser"},
        ]

        # Create or update the notifications
        for data in notifications_data:
            Notifications.objects.update_or_create(name=data["name"], defaults={"description": data["description"]})

        self.stdout.write(self.style.SUCCESS("Successfully seeded the notification table in database"))
