from django.urls import path

from .google_auth import AuthProvidersView, GoogleCallbackView, GoogleCredentialView, GoogleStartView
from .email_verification import EmailRegistrationView, EmailVerificationResendView, EmailVerificationStatusView, EmailVerificationVerifyView

urlpatterns = [
    path("providers", AuthProvidersView.as_view(), name="auth_providers"),
    path("register", EmailRegistrationView.as_view(), name="register"),
    path("email-verification/verify", EmailVerificationVerifyView.as_view(), name="email_verification_verify"),
    path("email-verification/resend", EmailVerificationResendView.as_view(), name="email_verification_resend"),
    path("email-verification/status", EmailVerificationStatusView.as_view(), name="email_verification_status"),
    path("google/start", GoogleStartView.as_view(), name="google_start"),
    path("google/callback", GoogleCallbackView.as_view(), name="google_callback"),
    path("google/credential", GoogleCredentialView.as_view(), name="google_credential"),
]
