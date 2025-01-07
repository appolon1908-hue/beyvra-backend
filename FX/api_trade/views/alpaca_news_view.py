from api_trade.utils.alpaca_util import get_today
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..scripts.alpaca_news import get_news


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="symbol",
            type=OpenApiTypes.STR,
            default="btc/usd",
        ),
        OpenApiParameter(
            name="sort",
            type=OpenApiTypes.STR,
            default="desc",
            enum=["asc", "desc"],
        ),
        OpenApiParameter(
            name="start",
            type=OpenApiTypes.DATE,
            default=get_today(),
        ),
        OpenApiParameter(
            name="end",
            type=OpenApiTypes.DATE,
            default=get_today(),
        ),
        OpenApiParameter(
            name="include_content",
            type=OpenApiTypes.BOOL,
            default=True,
            enum=[True, False],
        ),
        OpenApiParameter(
            name="exclude_contentless",
            type=OpenApiTypes.BOOL,
            default=True,
            enum=[True, False],
        ),
        OpenApiParameter(
            name="limit",
            type=OpenApiTypes.INT,
            default=10,
        ),
    ],
)
@api_view(["GET"])
def get_news_alpaca(request):
    """News Alpaca serializer.

    - Attributes:
        * ```symbol``` (str): The comma-separated list of symbols to query news for.
        * ```start``` (str): The start date for the data. If missing, the default value is the beginning of the current day.
        * ```end``` (str): The end date for the data. If missing, the default value is the current time.
        * ```sort``` (str): Sort articles by updated date.
        * ```include_content``` (bool): Boolean indicator to include content for news articles (if available)
        * ```exclude_contentless``` (bool): Boolean indicator to exclude news articles that do not contain content
        * ```limit``` (int): Limit of news items to be returned for given page. The default is 10
    """  # noqa
    try:
        result = get_news(request)
    except Exception as e:
        return Response(
            {"error": f"An error occurred: {e}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(result)
