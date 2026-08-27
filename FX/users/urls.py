from django.conf import settings
from django.urls import path

from users import views
from users.keycloak_bff import (
    KeycloakCallbackView,
    KeycloakConfigView,
    KeycloakCsrfView,
    KeycloakLoginView,
    KeycloakLogoutView,
    KeycloakPasswordResetView,
    KeycloakRegistrationView,
)

app_name = "user"

# Keycloak endpoints are always registered so disabled environments return a
# stable 503 contract. Local password and registration routes disappear at the
# controlled cutover, preventing two human credential authorities.
urlpatterns = [
    path("oidc/config/", KeycloakConfigView.as_view(), name="oidc_config"),
    path("oidc/login/", KeycloakLoginView.as_view(), name="oidc_login"),
    path("oidc/register/", KeycloakRegistrationView.as_view(), name="oidc_register"),
    path("oidc/password-reset/", KeycloakPasswordResetView.as_view(), name="oidc_password_reset"),
    path("oidc/callback/", KeycloakCallbackView.as_view(), name="oidc_callback"),
    path("oidc/csrf/", KeycloakCsrfView.as_view(), name="oidc_csrf"),
    path("oidc/logout/", KeycloakLogoutView.as_view(), name="oidc_logout"),
    path("get-user/<int:id>/", views.GetUserView.as_view(), name="get_user"),
    path("delete/", views.DeleteUserView.as_view(), name="delete"),
    path("me/", views.ManageUserView.as_view(), name="me"),
    path("token/refresh/", views.CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("guest-demo/", views.GuestDemoSessionView.as_view(), name="guest_demo_session"),
    path("disable_walkthrough/", views.DisableWalkthroughView.as_view(), name="disable_walkthrough"),
    path("send_phone_verification/", views.SendPhoneVerificationView.as_view(), name="send_phone_verification"),
    path("verify_phone/", views.VerifyPhoneCodeView.as_view(), name="verify_phone"),
    path("2fa-method/", views.UserSet2FAMethodView.as_view(), name="set_two_factor"),
    path("websocket_ticket/", views.websocket_ticket, name="websocket_ticket"),
    path("kyc/", views.KYCListCreateView.as_view(), name="kyc_list_create"),
    path("kyc/<int:pk>/", views.KYCUpdateView.as_view(), name="kyc_update"),
    path("kycfiles/", views.KYCFileListCreateView.as_view(), name="kycfile_list_create"),
    path("kycfiles/<int:pk>/", views.KYCFileDetailView.as_view(), name="kycfile_delete"),
    path("trading_statistics/", views.user_trading_statistics, name="user_trading_statistics"),
]

if settings.LOCAL_PASSWORD_AUTH_ENABLED:
    urlpatterns += [
        path("create/", views.CreateUserView.as_view(), name="create"),
        path("send_email_verification/", views.SendEmailVerificationView.as_view(), name="send_email_verification"),
        path("request_verification_email/", views.request_email_verification, name="request_verification_email"),
        path("verify_email/<uidb64>/<token>/", views.verify_email, name="verify_email"),
        path("token/", views.LoginView.as_view(), name="token_obtain_pair"),
        path("token/logout/", views.LogoutView.as_view(), name="token_logout"),
        path("generate_mfa_code/", views.EnableMFAView.as_view(), name="enable_mfa"),
        path("verify_mfa_code/", views.VerifyMFAView.as_view(), name="verify_mfa"),
        path("password_reset/", views.PasswordResetRequestView.as_view(), name="password_reset"),
        path("password_reset_confirm/<uidb64>/<token>/", views.password_reset_confirm, name="password_reset_confirm"),
        path("password_change/", views.password_change, name="password_change"),
    ]
