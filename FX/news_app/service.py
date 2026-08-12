from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from provider_governance.service import ProviderNotAvailable, resolve_provider

from .events import ingest_news
from .models import NewsArticle, NewsSource
from .newsdata import CapabilityNotAvailable, NewsDataClient, NewsDataError, decode_cursor, normalize_article, normalize_source, opaque_cursor

TTL = {"latest":300, "crypto":600, "market":600, "sources":86400}
PRODUCT = {"latest":"LATEST", "crypto":"CRYPTO", "market":"MARKET", "sources":"SOURCES", "archive":"ARCHIVE"}


def _credential(resolved):
    if resolved.credential_path:
        try: value=Path(resolved.credential_path).read_text(encoding="utf-8").strip()
        except OSError: raise ProviderNotAvailable("PROVIDER_NOT_AVAILABLE")
    else: value=getattr(settings,"NEWSDATA_API_KEY","").strip()
    if not value: raise ProviderNotAvailable("PROVIDER_NOT_AVAILABLE")
    return value


def _entitled(endpoint): return bool(getattr(settings, f"NEWSDATA_{endpoint.upper()}_ENTITLED", False))


def _authorize(request, endpoint):
    resolved=resolve_provider(provider_id="newsdata",provider_type="NEWS",product=PRODUCT[endpoint],symbol="*",region="GLOBAL",request_id=request.headers.get("X-Request-ID",""),correlation_id=request.headers.get("X-Correlation-ID",""),caller_service="canonical-news-api")
    if not _entitled(endpoint): raise CapabilityNotAvailable("CAPABILITY_NOT_AVAILABLE")
    return _credential(resolved)


def _params(request, endpoint):
    query=request.query_params
    mapped={"q":query.get("q"),"language":query.get("language"),"country":query.get("country"),"category":query.get("category"),"domain":query.get("source"),"page":decode_cursor(query.get("cursor")),"size":query.get("limit",10)}
    if endpoint=="crypto": mapped["coin"]=query.get("instrument")
    elif endpoint=="market": mapped["symbol"]=query.get("instrument")
    if endpoint=="archive": mapped.update(from_date=query.get("published_after"),to_date=query.get("published_before"))
    return {k:v for k,v in mapped.items() if v not in (None,"")}


def _serialize(article):
    return {"news_id":article.article_id,"headline":article.headline,"summary":article.summary,"content_preview":article.content_preview,"source_name":article.publisher,"source_id":article.source_id,"source_url":article.source_url,"article_url":article.canonical_url,"image_url":article.image_url,"published_at":article.published_at,"received_at":article.received_at,"language":article.language,"countries":article.countries,"categories":article.categories,"instrument_refs":article.affected_instruments,"keywords":article.keywords,"sentiment":article.sentiment,"provider_id":article.provider_id,"provider_article_id":article.provider_article_id,"provider_timestamp":article.provider_timestamp,"delayed":article.delayed,"stale":False,"provenance":{"provider_id":article.provider_id,"normalizer_version":article.normalizer_version}}


def _payload(canonical, endpoint):
    return {"article_id":canonical["news_id"],"provider_id":"newsdata","provider_article_id":canonical["provider_article_id"],"headline":canonical["headline"],"summary":canonical["summary"],"content_preview":canonical["content_preview"],"publisher":canonical["source_name"],"source_id":canonical["source_id"],"source_url":canonical["source_url"],"canonical_url":canonical["article_url"],"image_url":canonical["image_url"],"published_at":canonical["published_at"],"provider_timestamp":canonical["provider_timestamp"],"affected_instruments":canonical["instrument_refs"],"affected_assets":canonical["instrument_refs"],"affected_currencies":[],"countries":canonical["countries"],"categories":canonical["categories"],"keywords":canonical["keywords"],"sentiment":canonical["sentiment"],"language":canonical["language"],"delayed":canonical["delayed"],"raw_payload_hash":canonical["raw_payload_hash"],"normalizer_version":canonical["provenance"]["normalizer_version"],"endpoint":endpoint}


def fetch_newsdata(request, endpoint, article_id=None):
    if article_id:
        _authorize(request,"latest")
        try: return _serialize(NewsArticle.objects.get(article_id=article_id,provider_id="newsdata"))
        except NewsArticle.DoesNotExist: return None
    key=_authorize(request,endpoint)
    params=_params(request,endpoint)
    cache_key=f"newsdata:canonical:{endpoint}:{hash(frozenset(params.items()))}"
    cached=cache.get(cache_key)
    if cached is not None: return {**cached,"stale":False}
    client=NewsDataClient(key,archive_entitled=_entitled("archive"))
    try: raw=getattr(client,f"get_{endpoint}")(**params)
    except (NewsDataError,ValueError) as exc:
        if isinstance(exc,CapabilityNotAvailable): raise
        raise ProviderNotAvailable("PROVIDER_NOT_AVAILABLE")
    delayed=bool(getattr(settings,"NEWSDATA_DELAYED",True))
    if endpoint=="sources":
        results=[]
        with transaction.atomic():
            for item in raw["results"]:
                source=normalize_source(item); NewsSource.objects.update_or_create(source_id=source["source_id"],defaults=source); results.append(source)
    else:
        results=[]
        for item in raw["results"]:
            canonical=normalize_article(item,delayed=delayed); article,_event=ingest_news(_payload(canonical,endpoint)); results.append(_serialize(article))
    response={"results":results,"next_cursor":opaque_cursor(raw.get("nextPage")),"delayed":delayed,"stale":False}
    cache.set(cache_key,response,TTL.get(endpoint,300)); return response
