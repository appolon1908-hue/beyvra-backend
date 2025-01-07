from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from wallet.models import Currency


def set_currency_image(
    currency: Currency,
) -> File:
    # Open the image file
    with open(
        settings.BASE_DIR / f"wallet/management/commands/seed_images/{currency.name}.png",
        "rb",
    ) as image_file:
        # Wrap the file in a Django File object
        django_file = File(image_file)
        # set image of instance
        currency.image.save(f"{currency.name}.png", django_file, save=True)


class Command(BaseCommand):
    help = "Seeds the data in currency table"

    def handle(self, *args, **kwargs):
        # Define the initial data
        currencies = [
            {"name": "Đ", "symbol": "Đ", "longer_name": "Demo currency"},
            {"name": "USD", "symbol": "$", "longer_name": "Us dollar"},
            {"name": "USDT", "symbol": "₮", "longer_name": "USDT", "is_crypto": True},
            {"name": "EUR", "symbol": "€", "longer_name": "Euro"},
        ]

        # Create or update the notifications
        for currency in currencies:
            currency, _ = Currency.objects.update_or_create(
                name=currency["name"],
                symbol=currency["symbol"],
                longer_name=currency["longer_name"],
                is_crypto=currency.get("is_crypto", False),
            )
            # Assign the image file to the ImageField
            set_currency_image(currency=currency)

        self.stdout.write(self.style.SUCCESS("Successfully seeded the currency table in database"))
