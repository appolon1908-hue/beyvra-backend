from django.urls import path

from .views import EmptyCollectionView, EmptyDetailView, FeesView, OrderCancelView, OrderCollectionView, OrderDetailView, OrderPreviewView

urlpatterns = [
    path("orders/preview", OrderPreviewView.as_view()),
    path("orders", OrderCollectionView.as_view()),
    path("orders/<uuid:order_id>", OrderDetailView.as_view()),
    path("orders/<uuid:order_id>/cancel", OrderCancelView.as_view()),
    path("trades", EmptyCollectionView.as_view()),
    path("trades/<uuid:trade_id>", EmptyDetailView.as_view()),
    path("positions", EmptyCollectionView.as_view()),
    path("positions/<uuid:position_id>", EmptyDetailView.as_view()),
    path("accounts", EmptyCollectionView.as_view()),
    path("accounts/<uuid:account_id>", EmptyDetailView.as_view()),
    path("fees", FeesView.as_view()),
]
