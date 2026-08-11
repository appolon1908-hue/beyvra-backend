from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import AccountSession, OperatorRole
from .services import tenant_for


class SessionBoundJWTAuthentication(JWTAuthentication):
    """Validate session-bound tokens and require binding for privileged users."""

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
