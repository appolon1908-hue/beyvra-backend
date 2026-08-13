from rest_framework.throttling import SimpleRateThrottle


class IntegrationThrottle(SimpleRateThrottle):
    scope = "integration"
    fallback_rates = {"integration": "300/minute", "user_create": "30/minute", "import_upload": "5/hour", "import_action": "10/hour", "crm_inbound": "120/minute", "webhook_test": "5/minute", "webhook_retry": "10/hour"}
    def get_rate(self):
        return self.THROTTLE_RATES.get(self.scope, self.fallback_rates[self.scope])
    def get_cache_key(self, request, view):
        token = getattr(request, "service_token", None)
        if token:
            return self.cache_format % {"scope": self.scope, "ident": f"token:{token.id}"}
        if request.user and request.user.is_authenticated:
            return self.cache_format % {"scope": self.scope, "ident": f"user:{request.user.pk}"}
        return self.cache_format % {"scope": self.scope, "ident": f"ip:{self.get_ident(request)}"}


class UserCreateThrottle(IntegrationThrottle):
    scope = "user_create"


class ImportThrottle(IntegrationThrottle):
    scope = "import_upload"


class ImportActionThrottle(IntegrationThrottle):
    scope = "import_action"


class CRMInboundThrottle(IntegrationThrottle):
    scope = "crm_inbound"


class WebhookTestThrottle(IntegrationThrottle):
    scope = "webhook_test"


class WebhookRetryThrottle(IntegrationThrottle):
    scope = "webhook_retry"
