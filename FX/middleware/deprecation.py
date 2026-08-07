import logging

from prometheus_client import Counter

logger = logging.getLogger("codestra.deprecation")
legacy_requests = Counter("codestra_legacy_api_requests_total", "Requests to compatibility API routes", ("prefix",))

SUCCESSORS = {
    "/api/user/": "/api/v1/auth/",
    "/api/trades/": "/api/v1/trading/",
    "/api/wallet/": "/api/v1/wallets/",
    "/api/payment/": "/api/v1/deposits/",
    "/api/portfolio/": "/api/v1/wallets/",
    "/api/news/": "/api/v1/news",
    "/api/get-news/": "/api/v1/news",
    "/api/market-data/": "/api/v1/market/",
    "/api/charts/": "/api/v1/market/",
}


class LegacyApiDeprecationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        for prefix, successor in SUCCESSORS.items():
            if request.path.startswith(prefix):
                response["Deprecation"] = "true"
                response["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"
                response["Link"] = f'<{successor}>; rel="successor-version"'
                legacy_requests.labels(prefix=prefix).inc()
                logger.info("legacy_api_request", extra={"request_id": request.headers.get("X-Request-ID", ""), "legacy_prefix": prefix, "successor": successor})
                break
        return response
