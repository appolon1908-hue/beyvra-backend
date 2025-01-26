from django.urls import path
from wsnotifications import views

app_name = "wsnotifications"

urlpatterns = [
    path("", views.SetThresholdView.as_view(), name="threshold")
#     path("", views.TradeListCreateView.as_view(), name="trade_list_create"),
#     path("assets/", views.AssetListView.as_view(), name="asset_list"),
 ]