from django.urls import path

from . import views
from wallet import views as wallet_views

urlpatterns = [
    path("users/", views.FetchUserView.as_view(), name="admin_user_list"),
    path("users/<int:user_id>/", views.FetchUserDetailView.as_view(), name="admin_user_detail"),
    path("users/bulk/create/", views.BulkCreateUserView.as_view(), name="admin_bulk_create_user"),
    path("users/<int:user_id>/ban/", views.ban_user, name="admin_user_update"),
    path("users/<int:user_id>/unban/", views.unban_user, name="admin_user_update"),
    path("dashboard/over_views", views.admin_dashboard_overview, name="admin_dashboard_overview_view"),
    path("users/trades/<int:user_id>/", views.get_user_trading_activity, name="user_trades"), 
    path("users/trade_statistics/<int:user_id>/", views.get_user_trading_statistics, name="user_trades_statistics_view"),   
    path("users/kyc/verify/<int:user_id>/", views.verify_user_kyc, name="verify_user_kyc_status"),
    path("users/kyc/files/<int:file_id>/accept/", views.accept_kyc_file, name="accept_kyc_file_status"),
    path("users/kyc/files/<int:file_id>/reject/", views.reject_kyc_file, name="reject_kyc_file_status"), 
    path("users/<int:user_id>/document/status/", views.UserDocumentVerificationStatus.as_view()),
    path("users/<int:user_id>/face/status/", views.UserFaceVerificationStatus.as_view()),
    path("users/<int:user_id>/verification/status/", views.UserVerificationStatus.as_view()),
    path('users/search/', views.UserSearchView.as_view(), name='admin_user_search'),
    path("users/statuses/", views.UserStatusView.as_view(), name="admin_user_statuses"),
    path('users/import/', views.import_users, name='import_users'),
    path('users/export/', views.export_users, name='export_users'),
    path('users/search_users/', views.search_users, name='search_users'),
    path('users/<int:user_id>/roles/', views.user_roles, name='user-roles'),
]
