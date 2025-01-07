from django.urls import path
from security import views

app_name = "security"

urlpatterns = [
    path("user-activity/", views.UserActivityList.as_view()),
    # Global Settings
    path("trusted-devices/", views.TrustedDeviceList.as_view()),
    path('set-2fa/', views.SetGlobalTwoFactorAuth.as_view()),
    path('get-2fa/', views.GetGlobalTwoFactorAuth.as_view()),
    path('password-policy/', views.SetGlobalPasswordPolicy.as_view()),
    path('password-policy/get/', views.GetGlobalPasswordPolicy.as_view()),
    path('ip-whitelist/', views.IPWhitelist.as_view()),
    path('country-whitelist/', views.CountryWhitelist.as_view()),
    path('ip-whitelist/<int:pk>/delete/',
         views.IPWhitelistDeleteView.as_view()),
    path('country-whitelist/<int:pk>/delete/',
         views.CountryWhitelistDeleteView.as_view()),
    path('ip-restrictions/', views.IPRestrictionsView.as_view()),
    path('ip-blacklist/', views.IPBlacklistView.as_view()),
    path('ip-blacklist/<int:pk>/delete/',
         views.IPBlacklistDeleteView.as_view()),

    # User Security Settings
    path("users/<int:user_id>/ip_restriction/",
         views.UserIPRestrictionView.as_view()),
    path("users/<int:user_id>/set-2fa-type/",
         views.SetUser2FATypeView.as_view()),
    path("users/<int:user_id>/set-password-strength/",
         views.SetUserPasswordStrengthView.as_view()),
    path("users/<int:user_id>/set-password-length/",
         views.SetUserPasswordLengthView.as_view()),
    path("users/<int:user_id>/set-password-complexity/",
         views.SetUserPasswordComplexityView.as_view()),
    path("users/<int:user_id>/reset-settings/",
         views.ResetUserSettingsView.as_view()),
    path("users/<int:user_id>/ip-blacklist/",
         views.UserIPBlacklistView.as_view()),
    path("users/ip-blacklist/<int:pk>/",
         views.UserIPBlacklistUpdateDeleteView.as_view()),

]
