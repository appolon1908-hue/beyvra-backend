from django.contrib.auth import get_user_model

ACCOUNT_TYPES_URL = "/api/wallet/account_types/"


def detail_url(id):
    return f"{ACCOUNT_TYPES_URL}{id}/"


def create_user(email="user@example.come", password="testpass123"):
    """Create and return user."""
    return get_user_model().objects.create_user(email=email, password=password)
