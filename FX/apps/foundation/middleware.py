import time
from .observability import ENVIRONMENT, HTTP_DURATION, HTTP_REQUESTS

CANONICAL_PREFIXES=("/api/v1/auth/","/api/v1/me","/api/v1/demo/","/api/v1/market/","/api/v1/trading/","/api/v1/wallets/","/api/v1/notifications/","/api/v1/realtime/","/api/v1/status/")

class CanonicalHTTPMetricsMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        started=time.monotonic(); response=self.get_response(request)
        if request.path.startswith(CANONICAL_PREFIXES):
            match=getattr(request,"resolver_match",None)
            route="/" + str(getattr(match,"route","")).lstrip("/") if match else "unmatched"
            labels=(request.method,route,f"{response.status_code//100}xx",ENVIRONMENT)
            HTTP_REQUESTS.labels(*labels).inc(); HTTP_DURATION.labels(*labels).observe(time.monotonic()-started)
        return response
