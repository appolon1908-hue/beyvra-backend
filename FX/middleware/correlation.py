import uuid


class CorrelationIdMiddleware:
    """Attach a bounded internal correlation ID without exposing it publicly."""
    header = "X-Correlation-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get(self.header, "")
        correlation_id = supplied if len(supplied) <= 96 and supplied.replace("-", "").isalnum() else str(uuid.uuid4())
        request.correlation_id = correlation_id
        return self.get_response(request)
