from django.urls import path

from . import views

urlpatterns = [
    path("support/cases", views.SupportCaseListCreate.as_view()),
    path("support/cases/<uuid:case_id>", views.SupportCaseDetail.as_view()),
    path("support/cases/<uuid:case_id>/messages", views.SupportMessageCreate.as_view()),
    path("reports/activity", views.TransactionList.as_view()),
    path("reports/trades", views.TransactionList.as_view(history_type="TRADE")),
    path("reports/fees", views.TransactionList.as_view(history_type="FEE")),
    path("reports/transactions", views.TransactionList.as_view()),
    path("reports/trade-confirmations", views.TradeConfirmationList.as_view()),
    path("reports/statements", views.StatementList.as_view()),
    path("reports/exports", views.ReportJobListCreate.as_view()),
    path("reports/exports/<uuid:job_id>/download", views.ReportJobDownload.as_view()),
    path("privacy/exports", views.PrivacyExportListCreate.as_view()),
    path("privacy/exports/<uuid:job_id>/download", views.PrivacyExportDownload.as_view()),
    path("privacy/deletion-requests", views.AccountDeletionListCreate.as_view()),
    path("notifications/", views.NotificationList.as_view()),
    path("notifications/<uuid:notification_id>/read", views.NotificationRead.as_view()),
    path("notifications/read-all", views.NotificationReadAll.as_view()),
    path("notifications/preferences", views.PreferenceList.as_view()),
    path("security/sessions", views.SessionList.as_view()),
    path("security/sessions/<uuid:session_id>/revoke", views.SessionRevoke.as_view()),
    path("security/sessions/revoke-others", views.SessionRevokeOthers.as_view()),
]
