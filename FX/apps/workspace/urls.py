from django.urls import path

from .api import (
    WatchlistCollectionView,
    WatchlistDetailView,
    WatchlistItemCollectionView,
    WatchlistItemDetailView,
)


urlpatterns = [
    path("watchlists", WatchlistCollectionView.as_view(), name="watchlist-collection"),
    path(
        "watchlists/<uuid:watchlist_id>",
        WatchlistDetailView.as_view(),
        name="watchlist-detail",
    ),
    path(
        "watchlists/<uuid:watchlist_id>/items",
        WatchlistItemCollectionView.as_view(),
        name="watchlist-item-collection",
    ),
    path(
        "watchlists/<uuid:watchlist_id>/items/<str:instrument_id>",
        WatchlistItemDetailView.as_view(),
        name="watchlist-item-detail",
    ),
]
