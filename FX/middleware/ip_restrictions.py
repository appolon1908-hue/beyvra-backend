from django.core.exceptions import PermissionDenied
from django.utils.deprecation import MiddlewareMixin
from middleware.log_activity import log
from rest_framework import status
from security import models
from security.models import UserActivityActionTypes
from security.utils import get_logged_user
from users.utils import get_ip_address, get_user_location_mod


def check_ip_blacklist(ip_address):
    """Check if the IP address is in the blacklist."""
    if models.IPBlacklist.objects.filter(ip_address__iexact=ip_address).exists():
        return True
    return False


def check_ip_whitelist(ip_address):
    """Check if the IP address is in the whitelist."""
    return models.IPWhitelist.objects.filter(ip_address__iexact=ip_address).exists()


def check_country_blacklist(country):
    """Check if the country is in the blacklist."""
    if country and models.CountryBlacklist.objects.filter(country__iexact=country).exists():
        return True
    return False


def check_country_whitelist(user_location: dict):
    """Check if the country is in the whitelist."""
    country = user_location.get("country")
    return country and models.CountryWhitelist.objects.filter(country__iexact=country).exists()


def check_user_blacklist(user):
    """Check if the user is in the blacklist."""
    if user and models.UserIPBlacklist.objects.filter(user__email__iexact=user.email).exists():
        return True
    return False


class RestrictionMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Process view to check IP, country, and user blacklist/whitelist restrictions.
        """
        user = get_logged_user(request)
        ip_address = get_ip_address(request)
        user_location = get_user_location_mod(ip_address)

        # Set initial user activity info on request
        user_activity_info = getattr(request, "user_activity_info", {})
        user_activity_info.update({"user": user, "ip_address": ip_address, "user_location": user_location})

        request.user_activity_info = user_activity_info

        # Check country blacklist
        if isinstance(user_location, dict) and (country := user_location.get("country")):
            if check_country_blacklist(country):
                self._log_blacklist_action(
                    request=request,
                    user=user,
                    identifier=country,
                    action_type=UserActivityActionTypes.BLACKLISTED_COUNTRY.value,
                )
                raise PermissionDenied("Access denied")

        # Check IP blacklist
        if check_ip_blacklist(ip_address):
            self._log_blacklist_action(
                request=request,
                user=user,
                identifier=ip_address,
                action_type=UserActivityActionTypes.BLACKLISTED_IP.value,
            )
            raise PermissionDenied("Access denied")

        # Check user blacklist
        if check_user_blacklist(user):
            self._log_blacklist_action(
                request=request,
                user=user,
                identifier=user,
                action_type=UserActivityActionTypes.BLACKLISTED_USER.value,
            )
            raise PermissionDenied("Access denied")

    def process_response(self, request, response):
        user_activity_info = getattr(request, "user_activity_info", None)
        if user_activity_info:
            user = user_activity_info.get("user")
            ip_address = user_activity_info.get("ip_address")
            user_location = user_activity_info.get("user_location")

            # Check country whitelist
            if check_country_whitelist(user_location):
                self._log_whitelist_action(
                    request=request,
                    user=user,
                    identifier=user_location.get("country"),
                    action_type=UserActivityActionTypes.WHITELISTED_COUNTRY.value,
                )
            if check_country_whitelist(user_location) is False:
                # anonymous user
                self._log_whitelist_action(
                    request=request,
                    user=user,
                    action_type=UserActivityActionTypes.WHITELISTED_COUNTRY.value,
                )

            # Log whitelisted IP
            if check_ip_whitelist(ip_address):
                self._log_whitelist_action(
                    request=request,
                    user=user,
                    identifier=ip_address,
                    action_type=UserActivityActionTypes.WHITELISTED_IP.value,
                )

        return response

    def _log_blacklist_action(self, request, user, identifier, action_type, status_code=403):
        log(
            request=request,
            action_type=getattr(UserActivityActionTypes, action_type).value,
            desc=f"{action_type} -> {identifier}, blocked",
            err_msg=f"{action_type} -> {identifier}, blocked",
            accepted_status_code=(status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED),
            user=user,
            status_code=status_code,
        )

    def _log_whitelist_action(self, request, user, action_type, identifier="Unknown", status_code=200):
        log(
            request=request,
            action_type=getattr(UserActivityActionTypes, action_type).value,
            desc=f"{action_type} -> {identifier}, granted access",
            err_msg=f"{action_type} -> {identifier}, allowed",
            user=user,
            status_code=status_code,
        )
