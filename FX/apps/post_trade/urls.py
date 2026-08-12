from django.urls import path
from .api import ConfirmationDetail, ConfirmationList, PositionEffectDetail, PositionEffectList, ReconciliationStatus, SettlementDetail, SettlementList

urlpatterns = [path("settlements", SettlementList.as_view()), path("settlements/<uuid:resource_id>", SettlementDetail.as_view()), path("confirmations", ConfirmationList.as_view()), path("confirmations/<uuid:resource_id>", ConfirmationDetail.as_view()), path("position-effects", PositionEffectList.as_view()), path("position-effects/<uuid:resource_id>", PositionEffectDetail.as_view()), path("reconciliation/status", ReconciliationStatus.as_view())]
