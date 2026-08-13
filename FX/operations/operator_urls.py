from django.urls import path

from . import views

urlpatterns = [
    path("safety-flags", views.SafetyFlags.as_view()),
    path("accounts/<int:account_id>/freeze", views.OperatorFreeze.as_view()),
    path("accounts/<int:account_id>/summary", views.OperatorAccountSummary.as_view()),
    path("accounts/<int:account_id>/compliance", views.OperatorComplianceState.as_view()),
    path("accounts/<int:account_id>/financial", views.OperatorFinancialState.as_view()),
    path("accounts/<int:account_id>/statements", views.OperatorStatementIssue.as_view()),
    path("actions/<uuid:request_id>/approve", views.OperatorApprove.as_view()),
    path("actions/<uuid:request_id>/execute", views.OperatorExecute.as_view()),
    path("actions", views.OperatorActionCreate.as_view()),
    path("fraud/cases", views.OperatorFraudCases.as_view()),
    path("fraud/cases/<uuid:case_id>/status", views.OperatorFraudCaseUpdate.as_view()),
    path("support/cases", views.OperatorSupportCases.as_view()),
    path("support/cases/<uuid:case_id>/events", views.OperatorSupportEvent.as_view()),
    path("accounts/<int:account_id>/legal-holds", views.OperatorLegalHold.as_view()),
    path("audit-timeline", views.OperatorAuditTimeline.as_view()),
    path("control-state", views.OperatorControlState.as_view()),
    path("incidents", views.OperatorIncidents.as_view()),
    path("trading/halt", views.OperatorTradingHalt.as_view()),
    path("reconciliation/run", views.OperatorReconciliation.as_view()),
]
