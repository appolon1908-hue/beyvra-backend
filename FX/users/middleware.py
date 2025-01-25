import pytz
from django.utils.timezone import activate
from .models import MaintenanceMode
from django.http import HttpResponse
from django.shortcuts import redirect


class UserTimeZoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and hasattr(request.user, 'time_zone'):
            activate(pytz.timezone(request.user.time_zone))
        response = self.get_response(request)
        return response

class MaintenanceModeMiddleware:
    """
    Middleware to check if the site is in maintenance mode and block access to non-admin users.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        maintenance_mode = MaintenanceMode.objects.first()
        
        # Check if maintenance mode is active and the user is not an admin
        if maintenance_mode and maintenance_mode.is_active and not request.user.is_staff:
            return HttpResponse(
                f"Site is under maintenance. {maintenance_mode.message or ''}", 
                status=503
            )

        response = self.get_response(request)
        return response