from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from users import views

app_name = "user"

urlpatterns = [
    path("create/", views.CreateUserView.as_view(), name="create"),
    path("get-user/<int:id>/", views.GetUserView.as_view(), name="create"),
    path("delete/", views.DeleteUserView.as_view(), name="delete"),
    path(
        "send_email_verification/",
        views.SendEmailVerificationView.as_view(),
        name="send_email_verification",
    ),
    path("request_verification_email/", views.request_email_verification, name="request_verification_email"),
    path("verify_email/<uidb64>/<token>/", views.verify_email, name="verify_email"),
    path("me/", views.ManageUserView.as_view(), name="me"),
    path("token/", views.LoginView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("token/logout/", views.LogoutView.as_view(), name="token_logout"),
    path("guest-demo/", views.GuestDemoSessionView.as_view(), name="guest_demo_session"),
    path(
        "disable_walkthrough/",
        views.DisableWalkthroughView.as_view(),
        name="disable_walkthrough",
    ),
    path("generate_mfa_code/", views.EnableMFAView.as_view(), name="enable_mfa"),
    path("verify_mfa_code/", views.VerifyMFAView.as_view(), name="verify_mfa"),
    path(
        "send_phone_verification/",
        views.SendPhoneVerificationView.as_view(),
        name="send_phone_verification",
    ),
    path("verify_phone/", views.VerifyPhoneCodeView.as_view(), name="verify_phone"),
    path(
        "password_reset/",
        views.PasswordResetRequestView.as_view(),
        name="password_reset",
    ),
    path(
        "password_reset_confirm/<uidb64>/<token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),
    path("password_change/", views.password_change, name="password_change"),
    path("2fa-method/", views.UserSet2FAMethodView.as_view(), name="set_two_factor"),
    path("websocket_ticket/", views.websocket_ticket, name="websocket_ticket"),
    path("kyc/", views.KYCListCreateView.as_view(), name="kyc_list_create"),
    path("kyc/<int:pk>/", views.KYCUpdateView.as_view(), name="kyc_update"),
    path("kycfiles/", views.KYCFileListCreateView.as_view(), name="kycfile_list_create"),
    path("kycfiles/<int:pk>/", views.KYCFileDetailView.as_view(), name="kycfile_delete"),
    path("trading_statistics/", views.user_trading_statistics, name="user_trading_statistics"),
]
