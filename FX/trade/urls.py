from django.urls import path
from trade import views

app_name = "trade"

urlpatterns = [
    path("", views.TradeListCreateView.as_view(), name="trade_list_create"),
    path("assets/", views.AssetListView.as_view(), name="asset_list"),
]
