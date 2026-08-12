"""Governed, transactional news and calendar ingestion contracts."""

from django.db import transaction
from django.utils import timezone

from provider_governance.service import resolve_provider

from apps.foundation.services import enqueue_event
from .models import EconomicCalendarEvent, NewsArticle
from .observability import ARTICLES_DEDUPLICATED, ARTICLES_INGESTED, LAST_SUCCESS, NEWS_AGE

def _news(article):
    return {"news_id":article.article_id,"provider_id":article.provider_id,"provider_article_id":article.provider_article_id,"headline":article.headline,"summary":article.summary,"article_url":article.canonical_url,"published_at":article.published_at,"received_at":article.received_at,"instrument_refs":article.affected_instruments,"delayed":article.delayed,"provenance":{"provider_id":article.provider_id,"normalizer_version":article.normalizer_version}}


def _calendar(event):
    return {field:getattr(event,field) for field in ("event_id","provider_id","title","country","currency","importance","scheduled_at","actual_at","previous_value","forecast_value","actual_value","unit","affected_instruments","status")}


def _authorize(provider_id, provider_type, product, symbol):
    return resolve_provider(
        provider_id=provider_id, provider_type=provider_type, product=product,
        symbol=symbol or "*", region="GLOBAL", caller_service="news-calendar-ingestion",
    )


def _enqueue(*, event_type, channel, source, data, occurred_at):
    data = {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in data.items()}
    identifier = data.get("article_id") or data.get("event_id") or "unknown"
    return enqueue_event(
        aggregate_type="news_article" if event_type.startswith("news.") else "economic_event",
        aggregate_id=identifier, event_type=event_type, tenant_ref="public",
        payload={"channel": channel, "source": source, "data": data},
        occurred_at=occurred_at or timezone.now(),
    )


def ingest_news(payload):
    """Upsert one approved article and its event in the same transaction."""
    provider_id = payload["provider_id"]
    instruments = list(payload.get("affected_instruments") or [])
    _authorize(provider_id, "FINANCIAL_NEWS", "HEADLINES", instruments[0] if instruments else "*")
    return _ingest_news(payload, provider_id, instruments)


@transaction.atomic
def _ingest_news(payload, provider_id, instruments):
    existing = NewsArticle.objects.filter(provider_id=provider_id, provider_article_id=payload["provider_article_id"]).first()
    canonical_url = payload.get("canonical_url") or None
    if existing is None and canonical_url:
        existing = NewsArticle.objects.filter(canonical_url=canonical_url).first()
    if existing is not None and payload.get("raw_payload_hash") and existing.raw_payload_hash == payload["raw_payload_hash"]:
        ARTICLES_DEDUPLICATED.labels(provider_id).inc()
        return existing, None
    status = payload.get("status", NewsArticle.Status.PUBLISHED)
    article_id = existing.article_id if existing else payload["article_id"]
    values = {field: payload.get(field) for field in (
        "provider_id", "provider_article_id", "headline", "summary", "content_preview", "publisher", "source_id", "source_url", "canonical_url", "image_url", "published_at", "provider_timestamp", "delayed", "raw_payload_hash", "normalizer_version",
        "updated_at", "retracted_at", "importance", "affected_instruments", "affected_assets",
        "affected_currencies", "countries", "categories", "keywords", "sentiment", "language", "status",
    ) if field in payload}
    values["canonical_url"] = canonical_url
    article, created = NewsArticle.objects.update_or_create(article_id=article_id, defaults=values)
    suffix = "retracted" if status == NewsArticle.Status.RETRACTED else "published" if created else "updated"
    channel = f"news.instrument:{instruments[0]}" if len(instruments) == 1 else "news.market"
    event = _enqueue(event_type=f"news.article.{suffix}", channel=channel, source=provider_id, data=_news(article), occurred_at=payload.get("occurred_at"))
    ARTICLES_INGESTED.labels(provider_id, payload.get("endpoint", "unknown")).inc()
    LAST_SUCCESS.labels(provider_id, payload.get("endpoint", "unknown")).set(timezone.now().timestamp())
    NEWS_AGE.labels(provider_id, payload.get("endpoint", "unknown")).set(max(0, (timezone.now()-article.published_at).total_seconds()))
    return article, event


def ingest_economic_event(payload):
    """Upsert one approved calendar event and its event atomically."""
    provider_id = payload["provider_id"]
    instruments = list(payload.get("affected_instruments") or [])
    _authorize(provider_id, "ECONOMIC_CALENDAR", "EVENTS", instruments[0] if instruments else "*")
    return _ingest_economic_event(payload, provider_id, instruments)


@transaction.atomic
def _ingest_economic_event(payload, provider_id, instruments):
    existing = EconomicCalendarEvent.objects.filter(provider_id=provider_id, provider_event_id=payload["provider_event_id"]).first()
    status = payload.get("status", EconomicCalendarEvent.Status.SCHEDULED)
    event_id = existing.event_id if existing else payload["event_id"]
    values = {field: payload.get(field) for field in (
        "provider_id", "provider_event_id", "title", "country", "currency", "importance", "scheduled_at",
        "actual_at", "previous_value", "forecast_value", "actual_value", "unit", "affected_instruments", "status",
    ) if field in payload}
    item, created = EconomicCalendarEvent.objects.update_or_create(event_id=event_id, defaults=values)
    suffix = "cancelled" if status == EconomicCalendarEvent.Status.CANCELLED else "scheduled" if created else "updated"
    event = _enqueue(event_type=f"economic.event.{suffix}", channel="economic-calendar", source=provider_id, data=_calendar(item), occurred_at=payload.get("occurred_at"))
    return item, event


def envelope(event):
    return {
        "event_id": f"evt_{event.event_id.hex}", "event_type": event.event_type,
        "schema_version": event.schema_version,
        "occurred_at": event.occurred_at.isoformat(), "server_time": timezone.now().isoformat(),
        "correlation_id": str(event.correlation_id), "causation_id": str(event.causation_id) if event.causation_id else None,
        "tenant_ref": event.tenant_ref, "payload": event.payload,
    }


def jetstream_subject(event):
    return f"application.{event.event_type}"
