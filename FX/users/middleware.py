import pytz
from django.utils.timezone import activate

class UserTimeZoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'time_zone'):
            activate(pytz.timezone(request.user.time_zone))
        response = self.get_response(request)
        return response
