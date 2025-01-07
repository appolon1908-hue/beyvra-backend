from datetime import datetime

from alpaca.data.timeframe import TimeFrame
from django.core.exceptions import ValidationError
from rest_framework import status


def check_timeframe(string: str) -> TimeFrame:
    """Check timeframe."""
    if string.lower() == "minute":
        return TimeFrame.Minute
    elif string.lower() == "hour":
        return TimeFrame.Hour
    elif string.lower() == "week":
        return TimeFrame.Week
    elif string.lower() == "month":
        return TimeFrame.Month

    else:
        return TimeFrame.Day


def validate_date_range(start: str, end: str, today: str) -> None:
    """Validate the date range."""

    if today < start:
        raise ValidationError(
            "Start date is in the future.",
            params={"status": status.HTTP_400_BAD_REQUEST},
        )
    if end:
        if start > end:
            raise ValidationError(
                "Start date is greater than end date.",
                params={"status": status.HTTP_400_BAD_REQUEST},
            )


def validate_date_format(date_string):
    try:
        datetime.strptime(date_string, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_timeframe(timeframe: str) -> None:
    """Validate the timeframe."""
    if timeframe.lower() not in ["minute", "hour", "day", "week", "month"]:
        raise ValidationError(
            "Timeframe is not valid.",
            params={"status": status.HTTP_400_BAD_REQUEST},
        )


def response_dict_format(response: dict) -> dict:
    """Return a response dictionary with the timestamp
    in UNIX for example."""
    for field, data in response.items():
        response[field] = [{**response, "timestamp": response["timestamp"].timestamp()} for response in data]
    return response


def get_today() -> str:
    """Get today's date."""
    return datetime.now().strftime("%Y-%m-%d")


def list_of_lists_to_dict(list_data: list) -> dict:
    """Convert list of lists to dictionary."""
    return [order.model_dump() for order in list_data]


def format_orders_to_unix_timestamp(orders: list) -> list:
    """Format the orders to UNIX timestamp."""
    keys = [
        "created_at",
        "updated_at",
        "submitted_at",
        "filled_at",
        "expired_at",
        "canceled_at",
        "failed_at",
        "replaced_at",
    ]
    for order in orders:
        for key in keys:
            value = order.get(key)
            order[key] = value.timestamp() if value else None
    return orders


def format_to_unix_order_dict(order: dict) -> dict:
    """Format the order to dictionary."""
    keys = [
        "created_at",
        "updated_at",
        "submitted_at",
        "filled_at",
        "expired_at",
        "canceled_at",
        "failed_at",
        "replaced_at",
    ]
    for key in keys:
        value = order.get(key)
        order[key] = value.timestamp() if value else None
    return order


def paginate_alpaca_response(assets, request):
    page_size = int(request.query_params.get("page_size", 10))
    page_number = int(request.query_params.get("page_number", 1))
    start_index = (page_number - 1) * page_size
    end_index = start_index + page_size
    paginated_assets = assets[start_index:end_index]
    return paginated_assets
