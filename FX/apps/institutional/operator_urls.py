from django.urls import path
from . import api

urlpatterns = [
    path("accounts", api.OperatorAccountsView.as_view()), path("accounts/<uuid:account_id>", api.OperatorAccountDetailView.as_view()),
    path("accounts/<uuid:account_id>/ownership", api.OperatorOwnershipView.as_view()),
    path("subaccounts", api.OperatorSubaccountsView.as_view()), path("subaccounts/<uuid:subaccount_id>", api.OperatorSubaccountDetailView.as_view()),
    path("custody", api.OperatorCustodyView.as_view()), path("omnibus", api.OperatorOmnibusView.as_view()),
    path("segregated-accounts", api.OperatorSegregatedView.as_view()), path("allocation-groups", api.OperatorAllocationGroupsView.as_view()),
    path("allocations", api.OperatorAllocationsView.as_view()), path("clearing-brokers", api.OperatorClearingBrokersView.as_view()),
    path("clearing-relationships", api.OperatorClearingRelationshipsView.as_view()), path("broker-account-mappings", api.OperatorBrokerMappingsView.as_view()),
    path("settlement-mappings", api.OperatorSettlementMappingsView.as_view()), path("reconciliation", api.OperatorReconciliationView.as_view()),
    path("reconciliation/run", api.OperatorReconciliationView.as_view()),
]
