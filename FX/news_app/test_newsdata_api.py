from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.foundation.models import OutboxEvent
from provider_governance.service import ProviderNotAvailable
from .events import ingest_news
from .models import NewsArticle
from .newsdata import CapabilityNotAvailable


PAGE={"results":[],"next_cursor":"opaque","delayed":True,"stale":False}


class CanonicalNewsApiTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(email="newsdata@example.invalid",password="test",phone_number="+12025550177")
        self.client=APIClient(); self.client.force_authenticate(self.user)

    @patch("news_app.views.fetch_newsdata",return_value=PAGE)
    def test_crypto(self,fetch): self.assertEqual(self.client.get("/api/v1/news/crypto",{"instrument":"btc"}).json(),PAGE); fetch.assert_called_once()
    @patch("news_app.views.fetch_newsdata",return_value=PAGE)
    def test_market(self,fetch): self.assertEqual(self.client.get("/api/v1/news/market",{"instrument":"AAPL"}).status_code,200)
    @patch("news_app.views.fetch_newsdata",return_value=PAGE)
    def test_sources(self,fetch): self.assertEqual(self.client.get("/api/v1/news/sources").status_code,200)
    @patch("news_app.views.fetch_newsdata",return_value=PAGE)
    def test_archive_when_entitled(self,fetch): self.assertEqual(self.client.get("/api/v1/news/archive").status_code,200)
    @patch("news_app.views.fetch_newsdata",side_effect=CapabilityNotAvailable("CAPABILITY_NOT_AVAILABLE"))
    def test_archive_not_entitled(self,_fetch): self.assertEqual(self.client.get("/api/v1/news/archive").json(),{"code":"CAPABILITY_NOT_AVAILABLE"})
    @patch("news_app.views.fetch_newsdata",side_effect=ProviderNotAvailable("provider raw detail"))
    def test_provider_error_is_safe(self,_fetch): self.assertEqual(self.client.get("/api/v1/news/crypto").json(),{"code":"PROVIDER_NOT_AVAILABLE"})
    @patch("news_app.views.fetch_newsdata",side_effect=ValueError("unsupported provider parameter"))
    def test_invalid_filter_is_safe(self,_fetch): self.assertEqual(self.client.get("/api/v1/news/market").json(),{"code":"VALIDATION_FAILED"})

    @patch("news_app.events.resolve_provider")
    def test_duplicate_payload_creates_one_row_and_event(self,_resolve):
        from django.utils import timezone
        payload={"article_id":"newsdata:same","provider_id":"newsdata","provider_article_id":"same","headline":"Same","published_at":timezone.now(),"raw_payload_hash":"a"*64}
        first,event=ingest_news(payload); second,duplicate_event=ingest_news(payload)
        self.assertEqual(first.pk,second.pk); self.assertIsNone(duplicate_event); self.assertEqual(NewsArticle.objects.count(),1); self.assertEqual(OutboxEvent.objects.count(),1)
