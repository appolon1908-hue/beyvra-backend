import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DJANGO_SUPERUSER_EMAIL = os.getenv("DJANGO_SUPERUSER_EMAIL")
DJANGO_SUPERUSER_PASSWORD = os.getenv("DJANGO_SUPERUSER_PASSWORD")


class Command(BaseCommand):
    help = "Create a default superuser"
    if not DJANGO_SUPERUSER_EMAIL or DJANGO_SUPERUSER_EMAIL == "":
        raise ValueError("DJANGO_SUPERUSER_EMAIL not set")
    elif not DJANGO_SUPERUSER_PASSWORD or DJANGO_SUPERUSER_PASSWORD == "":
        raise ValueError("DJANGO_SUPERUSER_PASSWORD not set")

    def handle(self, *args, **options):
        user_model = get_user_model()
        superuser = user_model.objects.filter(email=DJANGO_SUPERUSER_EMAIL)
        if not superuser:
            user_model.objects.create_superuser(
                email=DJANGO_SUPERUSER_EMAIL,
                password=DJANGO_SUPERUSER_PASSWORD,
                # username=DJANGO_SUPERUSER_EMAIL,
            )
