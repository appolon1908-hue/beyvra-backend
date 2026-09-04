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
            description=(
                "Inclusive start date. If omitted, the provider uses the current UTC date."
            ),
        ),
        OpenApiParameter(
            name="end",
            type=OpenApiTypes.DATE,
            description=(
                "Inclusive end date. If omitted, the provider uses the current UTC date."
            ),
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
    """Return governed provider news without freezing date defaults into OpenAPI."""
    try:
        result = get_news(request)
    except Exception as exc:
        return Response(
            {"error": f"An error occurred: {exc}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(result)
