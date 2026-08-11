from django.urls import path

from . import views

urlpatterns = [
    path("safety-flags", views.SafetyFlags.as_view()),
    path("accounts/<int:account_id>/freeze", views.OperatorFreeze.as_view()),
    path("actions/<uuid:request_id>/approve", views.OperatorApprove.as_view()),
    path("actions/<uuid:request_id>/execute", views.OperatorExecute.as_view()),
    path("actions", views.OperatorActionCreate.as_view()),
    path("fraud/cases", views.OperatorFraudCases.as_view()),
    path("fraud/cases/<uuid:case_id>/status", views.OperatorFraudCaseUpdate.as_view()),
    path("support/cases", views.OperatorSupportCases.as_view()),
    path("support/cases/<uuid:case_id>/events", views.OperatorSupportEvent.as_view()),
    path("accounts/<int:account_id>/legal-holds", views.OperatorLegalHold.as_view()),
    path("audit-timeline", views.OperatorAuditTimeline.as_view()),
    path("reconciliation/run", views.OperatorReconciliation.as_view()),
]
