from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .utils import get_newsdata_news,get_newsdata_news_by_id


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="query",
            type=OpenApiTypes.STR,
            default="cryptocurrency",
        ),
        OpenApiParameter(
            name="size",
            type=OpenApiTypes.INT,
            default=10,
        ),
        OpenApiParameter(
            name="country",
            type=OpenApiTypes.STR,
            default="us",
        ),
    ],
)
@api_view(["GET"])
def get_news_newsdata(request):
    """News Newsdata serializer.

    - Attributes:
        * ```query``` (str): The query to search for news.
        * ```size``` (int): The number of news articles to return.
        * ```country``` (str): The country to search for news.
    """
    try:
        result = get_newsdata_news(request)
    except Exception as e:
        return Response(
            {"error": f"An error occurred: {e}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(result)



@extend_schema(
    parameters=[
        OpenApiParameter(
            name="query",
            type=OpenApiTypes.STR,
            default="cryptocurrency",
        ),
        OpenApiParameter(
            name="size",
            type=OpenApiTypes.INT,
            default=10,
        ),
        OpenApiParameter(
            name="country",
            type=OpenApiTypes.STR,
            default="us",
        ),
    ],
)
@api_view(["GET"])
def get_news_by_id(request, article_id):
    """Get a specific news item by its article_id from the Newsdata API.

    - Attributes:
        * ```article_id``` (str): The article ID to search for.
    """
    result = get_newsdata_news_by_id(request, article_id)
    return Response(result)


