import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.deprecation import MiddlewareMixin
from security.models import UserActivity
from users.utils import get_user_location

User = get_user_model()


class UserLoginActivityMiddleware(MiddlewareMixin):

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Process view to check login logic at the view level.
        This allows logging for login attempts even if the authentication backend
        raises an exception (e.g., incorrect password).
        """
        if request.path == "/api/user/token/" and request.method == "POST":
            try:
                # If content type is JSON, try to parse it
                if request.content_type == "application/json":
                    data = json.loads(request.body.decode("utf-8"))
                else:
                    data = request.POST
                email = data.get("email")
            except Exception as e:
                print("Error parsing request data in middleware: ", str(e))
                email = None
            if email:
                try:
                    user = User.objects.filter(email=email).first()
                    if user:
                        # if valid user log the activity
                        response = view_func(request, *view_args, **view_kwargs)
                        status_code = response.status_code

                        # Gather request metadata
                        user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]
                        ip_address = request.META.get("REMOTE_ADDR")
                        location = get_user_location(ip_address)
                        device_type = user_agent.split("/")[0] if user_agent else "Unknown"
                        device_model = user_agent.split("/")[1].split(" ")[0] if "/" in user_agent else "Unknown"

                        # Using transaction to ensure data integrity
                        with transaction.atomic():
                            UserActivity.objects.create(
                                user=user,
                                action_type="LOGIN",
                                action_status="SUCCESS" if status_code in [200, 201] else "FAILED",
                                description="Login attempt" if status_code in [200, 201] else "Failed login attempt",
                                ip_address=ip_address,
                                geolocation=location,
                                device_type=device_type,
                                device_model=device_model,
                                user_agent=user_agent,
                            )
                except Exception as e:
                    print("Error logging user activity in middleware: ", str(e))

        return None

    def process_response(self, request, response):
        return response
