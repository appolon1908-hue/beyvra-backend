from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime

from .service import fetch_newsdata
from .newsdata import CapabilityNotAvailable, NewsDataMalformed
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
    return {"article_id":article.article_id,"news_id":article.article_id,"provider_id":article.provider_id,"provider_article_id":article.provider_article_id,"headline":article.headline,"summary":article.summary,"content_preview":article.content_preview,"source_name":article.publisher,"source_id":article.source_id,"source_url":article.source_url,"article_url":article.canonical_url,"image_url":article.image_url,"published_at":article.published_at,"received_at":article.received_at,"language":article.language,"countries":article.countries,"categories":article.categories,"instrument_refs":article.affected_instruments,"keywords":article.keywords,"sentiment":article.sentiment,"provider_timestamp":article.provider_timestamp,"delayed":article.delayed,"stale":False,"provenance":{"provider_id":article.provider_id,"normalizer_version":article.normalizer_version}}


def _calendar(event):
    return {field: getattr(event, field) for field in (
        "event_id", "provider_id", "title", "country", "currency", "importance", "scheduled_at",
        "actual_at", "previous_value", "forecast_value", "actual_value", "unit", "affected_instruments", "status",
    )}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def news_list_v1(request):
    instrument = request.query_params.get("instrument", request.query_params.get("instrument_id", "*")).upper()
    try: _authorize(request,"newsdata","NEWS","LATEST",instrument)
    except ProviderNotAvailable: return _unavailable()
    limit=_limit(request)
    if limit is None: return Response({"code":"VALIDATION_FAILED"},status=400)
    queryset=NewsArticle.objects.exclude(status=NewsArticle.Status.RETRACTED).order_by("-published_at","-article_id")
    importance=request.query_params.get("importance")
    if importance: queryset=queryset.filter(importance=importance.upper())
    if request.query_params.get("category"): queryset=queryset.filter(categories__contains=[request.query_params["category"]])
    if request.query_params.get("source"): queryset=queryset.filter(source_id=request.query_params["source"])
    if request.query_params.get("language"): queryset=queryset.filter(language=request.query_params["language"])
    rows=[item for item in queryset[:limit+1] if instrument=="*" or instrument in item.affected_instruments]
    page=rows[:limit]
    return Response({"results":[_news(item) for item in page],"next_cursor":page[-1].article_id if len(rows)>limit else None,"delayed":any(item.delayed for item in page),"stale":False})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def news_detail_v1(request, article_id):
    item=fetch_newsdata(request,"latest",article_id=article_id)
    return Response(item) if item else Response({"code":"NOT_FOUND"},status=404)


def _provider_response(request, endpoint):
    try: return Response(fetch_newsdata(request,endpoint))
    except CapabilityNotAvailable: return Response({"code":"CAPABILITY_NOT_AVAILABLE"},status=404)
    except (ProviderNotAvailable,NewsDataMalformed): return _unavailable()
    except (TypeError,ValueError): return Response({"code":"VALIDATION_FAILED"},status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def news_crypto_v1(request): return _provider_response(request,"crypto")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def news_market_v1(request): return _provider_response(request,"market")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def news_sources_v1(request): return _provider_response(request,"sources")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def news_archive_v1(request): return _provider_response(request,"archive")


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
        result = fetch_newsdata(request,"latest")
    except ProviderNotAvailable:
        return Response({"code": "PROVIDER_NOT_AVAILABLE"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception:
        return _unavailable()

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
        result = fetch_newsdata(request,"latest",article_id=article_id)
    except ProviderNotAvailable:
        return Response({"code": "PROVIDER_NOT_AVAILABLE"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(result)
