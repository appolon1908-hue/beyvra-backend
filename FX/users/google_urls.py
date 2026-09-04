from django.conf import settings
from django.urls import path
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .email_verification import (
    EmailVerificationResendView,
    EmailVerificationStatusView,
    EmailVerificationVerifyView,
    StagingTestOtpView,
)
from .registration_safety import EmailRegistrationView


class AuthProvidersView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(
            {
                "google": {"enabled": False},
                "apple": {"enabled": False},
                "facebook": {"enabled": False},
            }
        )


class GoogleUnavailableView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response(
            {
                "code": "GOOGLE_PROVIDER_DISABLED",
                "message": "Google sign-in is unavailable in this environment.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    def get(self, request):
        return self.post(request)


urlpatterns = [
    path("providers", AuthProvidersView.as_view(), name="auth_providers"),
    path("google/start", GoogleUnavailableView.as_view(), name="google_start"),
    path("google/callback", GoogleUnavailableView.as_view(), name="google_callback"),
    path("google/credential", GoogleUnavailableView.as_view(), name="google_credential"),
]

if settings.LOCAL_PASSWORD_AUTH_ENABLED:
    urlpatterns += [
        path("register", EmailRegistrationView.as_view(), name="register"),
        path(
            "email-verification/verify",
            EmailVerificationVerifyView.as_view(),
            name="email_verification_verify",
        ),
        path(
            "email-verification/resend",
            EmailVerificationResendView.as_view(),
            name="email_verification_resend",
        ),
        path(
            "email-verification/status",
            EmailVerificationStatusView.as_view(),
            name="email_verification_status",
        ),
    ]

if settings.API_ENV == "staging" and settings.LOCAL_PASSWORD_AUTH_ENABLED:
    urlpatterns.append(
        path("test/otp", StagingTestOtpView.as_view(), name="staging_test_otp")
    )
