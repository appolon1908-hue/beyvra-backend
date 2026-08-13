import json
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings

from news_app.newsdata import CapabilityNotAvailable, NewsDataClient, NewsDataMalformed, NewsDataRateLimited, NewsDataUnauthorized, NewsDataUnavailable, decode_cursor, normalize_article, normalize_source, opaque_cursor, safe_url


ARTICLE={"status":"success","totalResults":1,"results":[{"article_id":"abc123","title":"Bitcoin market update","link":"https://example.com/a","image_url":"https://images.example.com/a.jpg","description":"Summary","content":"<b>provider text</b>","pubDate":"2026-08-11 08:00:00","source_id":"example","source_name":"Example","source_url":"https://example.com","language":"en","country":["us"],"category":["business"],"keywords":["bitcoin"],"coin":["btc"]}],"nextPage":"token-1"}
SOURCES={"status":"success","results":[{"id":"example","name":"Example","url":"https://example.com","country":"us","language":"en","category":["business"]}]}


class Response:
    def __init__(self,status=200,payload=None,headers=None,content=None):
        self.status_code=status; self._payload=payload; self.headers=headers or {}; self.content=content if content is not None else json.dumps(payload).encode()
    def json(self):
        if isinstance(self._payload,Exception): raise self._payload
        return self._payload


class Session:
    def __init__(self,*responses): self.responses=list(responses); self.calls=[]
    def get(self,*args,**kwargs): self.calls.append((args,kwargs)); value=self.responses.pop(0); return value() if callable(value) else value


class NewsDataClientTests(SimpleTestCase):
    def setUp(self): NewsDataClient.reset_circuit()
    def make_client(self,*responses,archive=False): return NewsDataClient("secret-not-printed",archive_entitled=archive,session=Session(*responses),environment="test")
    def test_latest_contract(self):
        c=self.make_client(Response(payload=ARTICLE)); assert c.get_latest(q="bitcoin",size=10)==ARTICLE; args,kwargs=c.session.calls[0]; self.assertEqual(args[0],"https://newsdata.io/api/1/latest"); self.assertEqual(kwargs["params"]["apikey"],"secret-not-printed")
    def test_crypto_contract(self): c=self.make_client(Response(payload=ARTICLE)); c.get_crypto(coin="btc"); self.assertEqual(c.session.calls[0][0][0],"https://newsdata.io/api/1/crypto")
    def test_market_contract(self): c=self.make_client(Response(payload=ARTICLE)); c.get_market(symbol="AAPL"); self.assertEqual(c.session.calls[0][0][0],"https://newsdata.io/api/1/market")
    def test_sources_contract(self): c=self.make_client(Response(payload=SOURCES)); self.assertEqual(c.get_sources(),SOURCES)
    def test_archive_requires_entitlement(self):
        with self.assertRaises(CapabilityNotAvailable): self.make_client().get_archive(from_date="2026-01-01")
    def test_archive_when_entitled(self): c=self.make_client(Response(payload=ARTICLE),archive=True); c.get_archive(from_date="2026-01-01"); self.assertIn("/archive",c.session.calls[0][0][0])
    def test_401_not_retried(self):
        c=self.make_client(Response(401,{"status":"error"}));
        with self.assertRaises(NewsDataUnauthorized): c.get_latest()
        self.assertEqual(len(c.session.calls),1)
    def test_403_not_retried(self):
        c=self.make_client(Response(403,{"status":"error"}));
        with self.assertRaises(NewsDataUnauthorized): c.get_latest()
        self.assertEqual(len(c.session.calls),1)
    @patch("news_app.newsdata.time.sleep",return_value=None)
    def test_429_respects_bounded_retry_after(self,_sleep):
        c=self.make_client(Response(429,{"status":"error"},{"Retry-After":"1"}),Response(payload=ARTICLE)); self.assertEqual(c.get_latest(),ARTICLE); _sleep.assert_called_once_with(1.0)
    def test_429_without_retry_after_fails(self):
        with self.assertRaises(NewsDataRateLimited): self.make_client(Response(429,{"status":"error"})).get_latest()
    def test_500_retries(self): c=self.make_client(Response(500,{"status":"error"}),Response(payload=ARTICLE)); self.assertEqual(c.get_latest(),ARTICLE)
    def test_timeout_retries_then_fails(self):
        def timeout(): raise requests.Timeout()
        with self.assertRaises(NewsDataUnavailable): self.make_client(timeout,timeout,timeout).get_latest()
    def test_malformed_json_fails_safely(self):
        with self.assertRaises(NewsDataMalformed): self.make_client(Response(payload=ValueError("raw provider"),content=b"no")).get_latest()
    def test_missing_results_fails(self):
        with self.assertRaises(NewsDataMalformed): self.make_client(Response(payload={"status":"success"})).get_latest()
    def test_response_size_bounded(self):
        with self.assertRaises(NewsDataMalformed): self.make_client(Response(payload=ARTICLE,content=b"x"*2_000_001)).get_latest()
    def test_unsupported_parameter_rejected_before_call(self):
        c=self.make_client()
        with self.assertRaises(ValueError): c.get_latest(host="evil.example")
        self.assertEqual(c.session.calls,[])
    def test_limit_bounded(self):
        with self.assertRaises(ValueError): self.make_client().get_latest(size=51)
    def test_circuit_opens(self):
        for _ in range(3):
            with self.assertRaises(NewsDataUnauthorized): self.make_client(Response(401,{"status":"error"})).get_latest()
        with self.assertRaises(NewsDataUnavailable): self.make_client(Response(payload=ARTICLE)).get_latest()
    def test_cursor_is_opaque_round_trip(self): self.assertEqual(decode_cursor(opaque_cursor("provider-token")),"provider-token")
    def test_invalid_cursor(self):
        with self.assertRaises(ValueError): decode_cursor("not-json")
    def test_normalize_article(self):
        item=normalize_article(ARTICLE["results"][0],delayed=True); self.assertEqual(item["provider_id"],"newsdata"); self.assertEqual(item["instrument_refs"],["BTC-USD"]); self.assertTrue(item["delayed"]); self.assertNotIn("apikey",item)
    def test_unknown_provider_symbol_is_not_promoted_to_instrument(self):
        self.assertEqual(normalize_article(ARTICLE["results"][0] | {"coin":["CAT"]},delayed=True)["instrument_refs"],[])
    def test_deterministic_fallback_identity(self):
        raw={**ARTICLE["results"][0]}; raw.pop("article_id"); self.assertEqual(normalize_article(raw,delayed=True)["news_id"],normalize_article(raw,delayed=True)["news_id"])
    def test_ambiguous_text_does_not_map_ticker(self): self.assertEqual(normalize_article(ARTICLE["results"][0] | {"coin":None},delayed=True)["instrument_refs"],[])
    def test_unsafe_urls_removed(self): self.assertIsNone(safe_url("javascript:alert(1)")); self.assertIsNone(safe_url("data:text/html,x"))
    def test_source_normalization(self):
        source=normalize_source(SOURCES["results"][0]); self.assertEqual(source["provider_id"],"newsdata"); self.assertEqual(source["domain"],"example.com")
    def test_invalid_timestamp(self):
        with self.assertRaises(NewsDataMalformed): normalize_article(ARTICLE["results"][0] | {"pubDate":"bad"},delayed=True)
