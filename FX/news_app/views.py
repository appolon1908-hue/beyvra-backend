from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime

from .utils import get_newsdata_news,get_newsdata_news_by_id
from provider_governance.service import ProviderNotAvailable
from provider_governance.service import resolve_provider
from .models import EconomicCalendarEvent, NewsArticle


def _unavailable():
    return Response({"code": "PROVIDER_NOT_AVAILABLE"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


def _authorize(request, provider_id, provider_type, product, symbol):
    return resolve_provider(
        provider_id=provider_id, provider_type=provider_type, product=product,
        symbol=symbol or "*", region="GLOBAL",
        request_id=request.headers.get("X-Request-ID", ""),
        correlation_id=request.headers.get("X-Correlation-ID", ""), caller_service="news-calendar-api",
    )


def _limit(request):
    try:
        value = int(request.query_params.get("limit", 25))
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= 100 else None


def _news(article):
    return {field: getattr(article, field) for field in (
        "article_id", "provider_id", "provider_article_id", "headline", "summary", "publisher",
        "canonical_url", "published_at", "updated_at", "retracted_at", "importance",
        "affected_instruments", "affected_assets", "affected_currencies", "language", "status",
    )}


def _calendar(event):
    return {field: getattr(event, field) for field in (
        "event_id", "provider_id", "title", "country", "currency", "importance", "scheduled_at",
        "actual_at", "previous_value", "forecast_value", "actual_value", "unit", "affected_instruments", "status",
    )}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def news_list_v1(request):
    instrument = request.query_params.get("instrument_id", "*").upper()
    try:
        _authorize(request, "newsdata", "FINANCIAL_NEWS", "HEADLINES", instrument)
    except ProviderNotAvailable:
        return _unavailable()
    limit = _limit(request)
    if limit is None:
        return Response({"code": "VALIDATION_FAILED"}, status=400)
    queryset = NewsArticle.objects.exclude(status=NewsArticle.Status.RETRACTED).order_by("-published_at", "-article_id")
    importance = request.query_params.get("importance")
    if importance:
        queryset = queryset.filter(importance=importance.upper())
    cursor = request.query_params.get("cursor")
    if cursor:
        queryset = queryset.filter(article_id__lt=cursor)
    rows = [item for item in queryset[: limit + 1] if instrument == "*" or instrument in item.affected_instruments]
    page = rows[:limit]
    return Response({"results": [_news(item) for item in page], "next_cursor": page[-1].article_id if len(rows) > limit else None})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def news_detail_v1(request, article_id):
    try:
        _authorize(request, "newsdata", "FINANCIAL_NEWS", "ARTICLE", "*")
    except ProviderNotAvailable:
        return _unavailable()
    return Response(_news(get_object_or_404(NewsArticle, article_id=article_id)))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def economic_calendar_v1(request):
    instrument = request.query_params.get("instrument_id", "*").upper()
    try:
        _authorize(request, "economic-calendar", "ECONOMIC_CALENDAR", "EVENTS", instrument)
    except ProviderNotAvailable:
        return _unavailable()
    start, end = parse_datetime(request.query_params.get("from", "")), parse_datetime(request.query_params.get("to", ""))
    if not start or not end or start >= end:
        return Response({"code": "VALIDATION_FAILED"}, status=400)
    queryset = EconomicCalendarEvent.objects.filter(scheduled_at__gte=start, scheduled_at__lte=end).order_by("scheduled_at", "event_id")[:500]
    rows = [item for item in queryset if instrument == "*" or instrument in item.affected_instruments]
    return Response({"results": [_calendar(item) for item in rows]})


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
    except ProviderNotAvailable:
        return Response({"code": "PROVIDER_NOT_AVAILABLE"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
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
    try:
        result = get_newsdata_news_by_id(request, article_id)
    except ProviderNotAvailable:
        return Response({"code": "PROVIDER_NOT_AVAILABLE"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(result)
