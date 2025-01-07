import shortuuid
from django.conf import settings


def generate_trader_id() -> int:
    """Generates a unique trader id for a user."""
    length = settings.SHORT_UUID_LEN

    if length in ("", None) or int(length) < 7:
        raise ValueError("The length of the trader id must be greater than 7.")

    length = int(
        shortuuid.ShortUUID(alphabet="0123456789").random(length=length),
    )
    return length
