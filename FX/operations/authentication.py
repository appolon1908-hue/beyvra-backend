from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework import exceptions
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import AccountSession, OperatorRole
from .services import tenant_for


class SessionBoundJWTAuthentication(JWTAuthentication):
    """Validate session-bound tokens and require binding for privileged users."""

    def authenticate(self, request):
        header = self.get_header(request)
        cookie_authenticated = header is None
        if header is None:
            raw_token = request.COOKIES.get("beyvra_access")
            if raw_token is None:
                return None
        else:
            raw_token = self.get_raw_token(header)
            if raw_token is None:
                return None
        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        if cookie_authenticated and request.method not in {"GET", "HEAD", "OPTIONS"}:
            self.enforce_csrf(request)
        return user, validated_token

    @staticmethod
    def enforce_csrf(request):
        check = CsrfViewMiddleware(lambda _: None)
        django_request = request._request
        check.process_request(django_request)
        reason = check.process_view(django_request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied("CSRF validation failed")

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        session_id = validated_token.get("session_id")
        tenant_id = tenant_for(user)
        if session_id:
            valid = AccountSession.objects.filter(
                session_id=session_id,
                tenant_id=tenant_id,
                account=user,
                revoked_at__isnull=True,
                expires_at__gt=validated_token.current_time,
            ).exists()
            if not valid:
                raise AuthenticationFailed("Session is no longer active.")
        elif (
            user.is_staff
            and OperatorRole.objects.filter(user=user, tenant_id=tenant_id).exists()
        ):
            raise AuthenticationFailed("A bound operator session is required.")
        return user
