from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from provider_governance.service import ProviderNotAvailable
from .events import ingest_economic_event, ingest_news
from apps.foundation.models import OutboxEvent
from .models import EconomicCalendarEvent, NewsArticle


class Phase5ContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="phase5@example.invalid", password="test", phone_number="+12025550188")
        self.client = APIClient(); self.client.force_authenticate(self.user)

    @patch("news_app.views.resolve_provider", side_effect=ProviderNotAvailable("PROVIDER_NOT_AVAILABLE"))
    @patch("requests.get")
    def test_news_denial_is_503_and_makes_zero_outbound_calls(self, outbound, _resolve):
        response = self.client.get("/api/v1/news", {"instrument_id": "BTC-USD"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "PROVIDER_NOT_AVAILABLE")
        outbound.assert_not_called()

    @patch("news_app.views.resolve_provider", side_effect=ProviderNotAvailable("PROVIDER_NOT_AVAILABLE"))
    @patch("requests.get")
    def test_calendar_denial_is_503_and_makes_zero_outbound_calls(self, outbound, _resolve):
        now = timezone.now()
        response = self.client.get("/api/v1/economic-calendar", {"instrument_id": "EUR-USD", "from": now.isoformat(), "to": (now + timedelta(days=1)).isoformat()})
        self.assertEqual(response.status_code, 503)
        outbound.assert_not_called()

    @patch("news_app.views.resolve_provider")
    def test_canonical_news_contract_is_bounded_and_filtered(self, _resolve):
        NewsArticle.objects.create(article_id="n1", provider_id="approved", provider_article_id="p1", headline="Headline", published_at=timezone.now(), importance="HIGH", affected_instruments=["BTC-USD"])
        response = self.client.get("/api/v1/news", {"instrument_id": "BTC-USD", "importance": "high", "limit": 25})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["article_id"], "n1")

    @patch("news_app.views.resolve_provider")
    def test_canonical_calendar_contract_filters_window_and_instrument(self, _resolve):
        now = timezone.now()
        EconomicCalendarEvent.objects.create(event_id="e1", provider_id="approved", provider_event_id="pe1", title="Rate", scheduled_at=now, affected_instruments=["EUR-USD"])
        response = self.client.get("/api/v1/economic-calendar", {"instrument_id": "EUR-USD", "from": (now - timedelta(hours=1)).isoformat(), "to": (now + timedelta(hours=1)).isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["event_id"], "e1")

    @patch("news_app.views.resolve_provider")
    def test_invalid_news_limit_is_rejected(self, _resolve):
        self.assertEqual(self.client.get("/api/v1/news", {"limit": 101}).status_code, 400)

    @patch("news_app.events.resolve_provider")
    def test_news_ingestion_deduplicates_and_writes_transactional_events(self, _resolve):
        now = timezone.now()
        base = {"article_id": "n1", "provider_id": "approved-test", "provider_article_id": "p1", "headline": "First", "canonical_url": "https://example.invalid/canonical", "published_at": now, "importance": "HIGH", "affected_instruments": ["BTC-USD"]}
        first, published = ingest_news(base)
        updated, changed = ingest_news({**base, "article_id": "ignored", "provider_article_id": "p2", "headline": "Updated", "status": "UPDATED", "updated_at": now})
        self.assertEqual(first.article_id, updated.article_id)
        self.assertEqual(NewsArticle.objects.count(), 1)
        self.assertEqual([published.event_type, changed.event_type], ["news.article.published", "news.article.updated"])
        self.assertEqual(OutboxEvent.objects.count(), 2)

    @patch("news_app.events.resolve_provider")
    def test_article_retraction_and_calendar_cancellation_are_events(self, _resolve):
        now = timezone.now()
        article = {"article_id": "n2", "provider_id": "approved-test", "provider_article_id": "p2", "headline": "Article", "published_at": now, "affected_instruments": ["BTC-USD"]}
        ingest_news(article)
        _, retracted = ingest_news({**article, "status": "RETRACTED", "retracted_at": now})
        event = {"event_id": "e2", "provider_id": "approved-test", "provider_event_id": "pe2", "title": "Rate", "scheduled_at": now, "affected_instruments": ["EUR-USD"]}
        ingest_economic_event(event)
        _, cancelled = ingest_economic_event({**event, "status": "CANCELLED"})
        self.assertEqual(retracted.event_type, "news.article.retracted")
        self.assertEqual(cancelled.event_type, "economic.event.cancelled")
