from django.urls import path

from .operator_platform import (
    OperatorAuditEventView,
    OperatorHaltListView,
    OperatorOrderListView,
    OperatorProviderHealthView,
    OperatorReconciliationBreaksView,
)
from apps.surveillance.api import ApproveRestriction, RestrictionList


urlpatterns = [
    path("orders", OperatorOrderListView.as_view(), name="operator-order-list"),
    path("halts", OperatorHaltListView.as_view(), name="operator-halt-list"),
    path("providers/health", OperatorProviderHealthView.as_view(), name="operator-provider-health"),
    path("reconciliation/breaks", OperatorReconciliationBreaksView.as_view(), name="operator-reconciliation-breaks"),
    path("audit/events", OperatorAuditEventView.as_view(), name="operator-audit-events"),
    path("limits/proposals", RestrictionList.as_view(), name="operator-limit-proposals"),
    path("limits/<uuid:restriction_id>/approve", ApproveRestriction.as_view(), name="operator-limit-approve"),
]
