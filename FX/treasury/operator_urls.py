from django.urls import path
from .api import *

urlpatterns = [
    path("accounts", OperatorAccountsView.as_view()), path("accounts/<uuid:account_id>", OperatorAccountsView.as_view()),
    path("transfer-plans", OperatorPlansView.as_view()),
    path("transfer-plans/<uuid:plan_id>/simulate", OperatorPlanActionView.as_view(), {"action": "simulate"}),
    path("transfer-plans/<uuid:plan_id>/cancel", OperatorPlanActionView.as_view(), {"action": "cancel"}),
    path("stress-scenarios", OperatorStressScenariosView.as_view()), path("stress/run", OperatorStressRunView.as_view()),
    path("exceptions", OperatorExceptionsView.as_view()), path("exceptions/<uuid:exception_id>", OperatorExceptionsView.as_view()),
    path("exceptions/<uuid:exception_id>/assign", OperatorExceptionActionView.as_view(), {"action": "assign"}),
    path("exceptions/<uuid:exception_id>/escalate", OperatorExceptionActionView.as_view(), {"action": "escalate"}),
    path("exceptions/<uuid:exception_id>/resolve", OperatorExceptionActionView.as_view(), {"action": "resolve"}),
    path("reconciliation", OperatorReconciliationView.as_view()), path("reconciliation/run", OperatorReconciliationView.as_view()),
    path("funding-requirements/<uuid:requirement_id>/evidence", OperatorEvidenceView.as_view()),
]
