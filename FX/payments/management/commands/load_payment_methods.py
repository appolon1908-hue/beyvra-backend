from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from payments.models import PaymentMethod


def set_image(
    obj: PaymentMethod,
) -> File:
    # Open the image file
    with open(
        settings.BASE_DIR /
            f"payments/management/commands/seed_images/{obj.name}.svg",
        "rb",
    ) as image_file:
        # Wrap the file in a Django File object
        django_file = File(image_file)
        # set image of instance
        obj.icon.save(f"{obj.name}.svg", django_file, save=True)


class Command(BaseCommand):
    help = "Seeds the data in pyment methods table"

    def handle(self, *args, **kwargs):
        # Define the initial data
        methods = [
            {"name": "UPI", "type": "bank"},
            {"name": "Bank cards", "type": "bank"},
            {"name": "NetBanking", "type": "bank"},
            {"name": "AstroPay Card", "type": "epayment"},
            {"name": "Skrill", "type": "epayment"},
            {"name": "Neteller", "type": "epayment"},
            {"name": "Perfect Money", "type": "epayment"},
            {"name": "BinancePay", "type": "epayment"},
            {"name": "USDT (TRC20)", "type": "crypto"},
            {"name": "USDT (ERC20)", "type": "crypto"},
            {"name": "USDT (BSC BEP-20)", "type": "crypto"},
            {"name": "Bitcoin", "type": "crypto"},
            {"name": "Ethereum", "type": "crypto"},
            {"name": "Shiba Inu", "type": "crypto"},
            {"name": "Dogecoin (BSC BEP-20)", "type": "crypto"},
            {"name": "Solana", "type": "crypto"},
            {"name": "DAI (BSC BEP-20)", "type": "crypto"},
            {"name": "Binance Coin (BSC BEP-20)", "type": "crypto"},
            {"name": "TRX", "type": "crypto"},
            {"name": "XRP", "type": "crypto"},
            # {"name": "Pay Retailers", "type": "epayment"},
            # {"name": "Bitpay", "type": "crypto"},
            # {"name": "Adyen", "type": "epayment"}
        ]

        # Create or update the notifications
        for method in methods:
            obj, _ = PaymentMethod.objects.update_or_create(
                name=method["name"],
                type=method["type"],
            )
            # Assign the image file to the ImageField
            set_image(obj=obj)

        self.stdout.write(self.style.SUCCESS(
            "Successfully seeded the payment methods table"))
