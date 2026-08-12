"""Governed NewsData transport and provider-neutral normalization."""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils.dateparse import parse_datetime

from .observability import PROVIDER_DURATION, PROVIDER_FAILURES, PROVIDER_RATE_LIMITED, PROVIDER_REQUESTS

BASE_URL = "https://newsdata.io/api/1"
ALLOWED_HOST = "newsdata.io"
NORMALIZER_VERSION = "newsdata-v1"
CANONICAL_INSTRUMENTS = {
    "BTC": "BTC-USD", "BITCOIN": "BTC-USD", "ETH": "ETH-USD", "ETHEREUM": "ETH-USD",
    "BNB": "BNB-USD", "SOL": "SOL-USD", "SOLANA": "SOL-USD", "XRP": "XRP-USD",
    "AAPL": "AAPL", "MSFT": "MSFT", "TSLA": "TSLA",
}
ENDPOINTS = {"latest":"latest", "crypto":"crypto", "market":"market", "sources":"sources", "archive":"archive"}
ARTICLE_PARAMS = {"q","language","country","category","domain","timeframe","page","size"}
CRYPTO_PARAMS = ARTICLE_PARAMS | {"coin"}
MARKET_PARAMS = ARTICLE_PARAMS | {"symbol"}
SOURCE_PARAMS = {"language","country","category"}
ARCHIVE_PARAMS = ARTICLE_PARAMS | {"from_date","to_date"}


class NewsDataError(Exception): pass
class NewsDataUnavailable(NewsDataError): pass
class NewsDataUnauthorized(NewsDataError): pass
class NewsDataRateLimited(NewsDataError): pass
class NewsDataMalformed(NewsDataError): pass
class CapabilityNotAvailable(NewsDataError): pass


@dataclass
class _Circuit:
    failures: int = 0
    opened_at: float | None = None
    half_open_inflight: bool = False


class NewsDataClient:
    """No business/UI logic; bounded, allowlisted NewsData transport only."""
    _circuit = _Circuit()
    _lock = threading.Lock()

    def __init__(self, api_key: str, *, archive_entitled: bool = False, session=None, environment=None, clock=time.monotonic):
        if not api_key or not api_key.strip(): raise NewsDataUnavailable("PROVIDER_NOT_AVAILABLE")
        self._api_key = api_key.strip()
        self.archive_entitled = archive_entitled
        self.session = session or requests.Session()
        self.environment = environment or getattr(settings, "DEPLOYMENT_ENV", "local")
        self.clock = clock
        self.connect_timeout = 2.0
        self.request_timeout = 6.0
        self.overall_deadline = 12.0
        self.max_attempts = 3
        self.max_response_bytes = 2_000_000

    def get_latest(self, **params): return self._request("latest", params, ARTICLE_PARAMS)
    def get_crypto(self, **params): return self._request("crypto", params, CRYPTO_PARAMS)
    def get_market(self, **params): return self._request("market", params, MARKET_PARAMS)
    def get_sources(self, **params): return self._request("sources", params, SOURCE_PARAMS)
    def get_archive(self, **params):
        if not self.archive_entitled: raise CapabilityNotAvailable("CAPABILITY_NOT_AVAILABLE")
        return self._request("archive", params, ARCHIVE_PARAMS)
    def health(self): return {"provider_id":"newsdata", "available":self._allow_request(False), "archive":self.archive_entitled}

    @classmethod
    def reset_circuit(cls):
        with cls._lock: cls._circuit = _Circuit()

    def _allow_request(self, reserve=True):
        with self._lock:
            circuit = type(self)._circuit
            if circuit.opened_at is None: return True
            if self.clock() - circuit.opened_at < 30: return False
            if circuit.half_open_inflight: return False
            if reserve: circuit.half_open_inflight = True
            return True

    def _record_success(self):
        with self._lock: type(self)._circuit = _Circuit()

    def _record_failure(self):
        with self._lock:
            circuit=type(self)._circuit
            circuit.half_open_inflight = False
            circuit.failures += 1
            if circuit.failures >= 3: circuit.opened_at = self.clock()

    def _request(self, endpoint, supplied, allowed):
        if not self._allow_request(): raise NewsDataUnavailable("PROVIDER_NOT_AVAILABLE")
        params = {k:v for k,v in supplied.items() if v not in (None, "")}
        unsupported = set(params) - allowed
        if unsupported: raise ValueError("Unsupported news filter")
        if "size" in params and not 1 <= int(params["size"]) <= 50: raise ValueError("Invalid limit")
        params["apikey"] = self._api_key
        url = f"{BASE_URL}/{ENDPOINTS[endpoint]}"
        if urlparse(url).hostname != ALLOWED_HOST: raise NewsDataUnavailable("PROVIDER_NOT_AVAILABLE")
        started = self.clock(); last_error = None
        for attempt in range(self.max_attempts):
            if self.clock() - started >= self.overall_deadline: break
            try:
                response = self.session.get(url, params=params, timeout=(self.connect_timeout, self.request_timeout), allow_redirects=False)
                if len(response.content) > self.max_response_bytes: raise NewsDataMalformed("PROVIDER_NOT_AVAILABLE")
                if response.status_code in (401,403): raise NewsDataUnauthorized("PROVIDER_NOT_AVAILABLE")
                if response.status_code == 429:
                    PROVIDER_RATE_LIMITED.labels("newsdata",endpoint,"rate_limited",self.environment).inc()
                    retry_after = min(float(response.headers.get("Retry-After", "0") or 0), 2.0)
                    if attempt + 1 < self.max_attempts and retry_after and self.clock() - started + retry_after < self.overall_deadline:
                        time.sleep(retry_after); continue
                    raise NewsDataRateLimited("PROVIDER_NOT_AVAILABLE")
                if 500 <= response.status_code < 600:
                    last_error = NewsDataUnavailable("PROVIDER_NOT_AVAILABLE")
                    if attempt + 1 < self.max_attempts: continue
                    raise last_error
                if response.status_code >= 400: raise ValueError("Invalid provider request")
                try: payload = response.json()
                except (ValueError, json.JSONDecodeError): raise NewsDataMalformed("PROVIDER_NOT_AVAILABLE")
                self._validate(payload, endpoint); self._record_success()
                PROVIDER_REQUESTS.labels("newsdata",endpoint,"success",self.environment).inc()
                PROVIDER_DURATION.labels("newsdata",endpoint,"success",self.environment).observe(self.clock()-started)
                return payload
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = NewsDataUnavailable("PROVIDER_NOT_AVAILABLE")
                if attempt + 1 >= self.max_attempts: break
            except (NewsDataUnauthorized, NewsDataRateLimited, NewsDataMalformed, ValueError):
                self._record_failure(); PROVIDER_FAILURES.labels("newsdata",endpoint,"safe_error",self.environment).inc(); raise
        self._record_failure(); PROVIDER_FAILURES.labels("newsdata",endpoint,"unavailable",self.environment).inc()
        raise last_error or NewsDataUnavailable("PROVIDER_NOT_AVAILABLE")

    @staticmethod
    def _validate(payload, endpoint):
        if not isinstance(payload, dict) or payload.get("status") not in ("success", "error"):
            raise NewsDataMalformed("PROVIDER_NOT_AVAILABLE")
        if payload.get("status") == "error": raise NewsDataUnavailable("PROVIDER_NOT_AVAILABLE")
        if not isinstance(payload.get("results"), list): raise NewsDataMalformed("PROVIDER_NOT_AVAILABLE")


def opaque_cursor(provider_cursor: str | None) -> str | None:
    if not provider_cursor: return None
    return base64.urlsafe_b64encode(json.dumps({"v":1,"p":provider_cursor},separators=(",",":")).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> str | None:
    if not cursor: return None
    try:
        value=json.loads(base64.urlsafe_b64decode(cursor + "="*(-len(cursor)%4)))
        return value["p"] if value.get("v")==1 and isinstance(value.get("p"),str) else None
    except Exception: raise ValueError("Invalid cursor")


def safe_url(value: Any) -> str | None:
    if not value: return None
    try: parsed=urlparse(str(value))
    except ValueError: return None
    return str(value) if parsed.scheme == "https" and parsed.hostname else None


def _strings(value): return [str(v)[:128] for v in value] if isinstance(value,list) else []


def normalize_article(raw: dict[str,Any], *, delayed: bool) -> dict[str,Any]:
    if not isinstance(raw,dict) or not str(raw.get("title") or "").strip(): raise NewsDataMalformed("PROVIDER_NOT_AVAILABLE")
    published=parse_datetime(str(raw.get("pubDate") or ""))
    if published is None: raise NewsDataMalformed("PROVIDER_NOT_AVAILABLE")
    provider_id=str(raw.get("article_id") or "").strip()
    if not provider_id:
        stable={"title":raw.get("title"),"link":safe_url(raw.get("link")),"pubDate":published.isoformat(),"source_id":raw.get("source_id")}
        provider_id=hashlib.sha256(json.dumps(stable,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    instrument_refs=[]
    for symbol in _strings(raw.get("symbol") or raw.get("coin")):
        normalized=symbol.strip().upper()
        canonical=CANONICAL_INSTRUMENTS.get(normalized)
        if canonical: instrument_refs.append(canonical)
    canonical={"news_id":f"newsdata:{provider_id}","headline":str(raw["title"]).strip()[:512],"summary":str(raw.get("description") or "")[:4000],"content_preview":str(raw.get("content") or "")[:1000],"source_name":str(raw.get("source_name") or "")[:255],"source_id":str(raw.get("source_id") or "")[:255],"source_url":safe_url(raw.get("source_url")),"article_url":safe_url(raw.get("link")),"image_url":safe_url(raw.get("image_url")),"published_at":published,"received_at":datetime.now(timezone.utc),"language":str(raw.get("language") or "")[:16],"countries":_strings(raw.get("country")),"categories":_strings(raw.get("category")),"instrument_refs":sorted(set(instrument_refs)),"keywords":_strings(raw.get("keywords")),"sentiment":str(raw.get("sentiment") or "")[:32],"provider_id":"newsdata","provider_article_id":provider_id,"provider_timestamp":published,"delayed":bool(delayed),"provenance":{"provider_id":"newsdata","normalizer_version":NORMALIZER_VERSION}}
    canonical["raw_payload_hash"]=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    return canonical


def normalize_source(raw):
    if not isinstance(raw,dict) or not raw.get("id") or not raw.get("name"): raise NewsDataMalformed("PROVIDER_NOT_AVAILABLE")
    url=safe_url(raw.get("url")); domain=str(raw.get("domain") or (urlparse(url).hostname if url else "") or "")
    return {"source_id":str(raw["id"]),"name":str(raw["name"]),"domain":domain,"url":url,"country":str(raw.get("country") or ""),"language":str(raw.get("language") or ""),"categories":_strings(raw.get("category")),"provider_id":"newsdata","active":True}
