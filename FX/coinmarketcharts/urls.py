from django.urls import path
from .views import map
from .views import info
from .views import listings
from .views import quotes

urlpatterns = [
    path("map/", map.CryptocurrencyMapView.as_view(), name="map"),
    path("info/", info.CryptocurrencyInfoView.as_view(), name="info"),
    path("listings/latest/", listings.CryptocurrencyListinglatestView.as_view(), name="listings_latest"),
    path("listings/historical/", listings.CryptocurrencyListingHistoricalView.as_view(), name="listings_historical"),
    path("quotes/latest/", quotes.CryptocurrencyQuotesLatestView.as_view(), name="quotes_latest"),
]
