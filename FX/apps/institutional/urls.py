from django.urls import path
from . import api

urlpatterns = [
    path("account", api.AccountView.as_view()), path("account/hierarchy", api.HierarchyView.as_view()),
    path("subaccounts", api.SubaccountListView.as_view()), path("subaccounts/<uuid:subaccount_id>", api.SubaccountDetailView.as_view()),
    path("subaccounts/<uuid:subaccount_id>/positions", api.PositionsView.as_view()), path("subaccounts/<uuid:subaccount_id>/orders", api.OrdersView.as_view()),
    path("subaccounts/<uuid:subaccount_id>/trades", api.TradesView.as_view()), path("subaccounts/<uuid:subaccount_id>/risk", api.SubaccountRiskView.as_view()),
    path("portfolio", api.PortfolioView.as_view()), path("positions", api.InstitutionPositionsView.as_view()),
    path("orders", api.EmptyInstitutionResourceView.as_view()), path("trades", api.EmptyInstitutionResourceView.as_view()),
    path("exposure", api.ExposureView.as_view()), path("risk", api.RiskView.as_view()),
    path("allocation-groups", api.AllocationGroupListView.as_view()), path("allocation-groups/<uuid:group_id>", api.AllocationGroupDetailView.as_view()),
    path("allocations", api.AllocationListView.as_view()), path("allocations/<uuid:allocation_id>", api.AllocationDetailView.as_view()),
    path("custody/structure", api.CustodyStructureView.as_view()), path("reconciliation/status", api.ReconciliationStatusView.as_view()),
]
