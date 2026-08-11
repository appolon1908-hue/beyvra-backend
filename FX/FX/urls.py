"""
URL configuration for FX project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from users.views import GuestDemoSessionView, ManageUserView, SessionResolveView
from trade.demo_engine import DemoConfigView, DemoOrderView, DemoTradeListView, DemoWalletRefillView, DemoWalletView, WorkspaceBootstrapView
from ws import v2 as realtime_v2
from news_app import views as news_views
from users import urls as user_urls

urlpatterns = [
    path("health/", include("apps.foundation.health_urls")),
    path("", include("django_prometheus.urls")),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/frontendadmin/90210/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    path("api/user/", include("users.urls")),
    # Canonical aliases delegate to the existing views. Legacy routes remain
    # compatibility-only and are measured by deprecation middleware.
    path("api/v1/auth/", include((user_urls.urlpatterns, "canonical_auth"), namespace="canonical_auth")),
    path("api/v1/auth/", include("users.google_urls")),
    path("api/v1/me/", ManageUserView.as_view(), name="me_v1"),
    path("api/v1/notifications/", include("notifications.urls")),
    path("api/v1/demo/sessions", GuestDemoSessionView.as_view(), name="guest_demo_session_v1"),
    path("api/v1/session", SessionResolveView.as_view(), name="session_resolve_v1"),
    path("api/v1/workspace/bootstrap", WorkspaceBootstrapView.as_view(), name="workspace_bootstrap_v1"),
    path("api/v1/demo/orders", DemoOrderView.as_view(), name="demo_order_v1"),
    path("api/v1/demo/config", DemoConfigView.as_view(), name="demo_config_v1"),
    path("api/v1/demo/trades", DemoTradeListView.as_view(), name="demo_trades_v1"),
    path("api/v1/demo/wallet/refill", DemoWalletRefillView.as_view(), name="demo_wallet_refill_v1"),
    path("api/v1/demo/wallet", DemoWalletView.as_view(), name="demo_wallet_v1"),
    path("api/v1/realtime/v2/connection-token", realtime_v2.connection_token, name="realtime_v2_connection_token"),
    path("api/v1/realtime/v2/subscription-token", realtime_v2.subscription_token, name="realtime_v2_subscription_token"),
    path("api/v1/realtime/v2/authorize-subscription", realtime_v2.authorize_subscription, name="realtime_v2_authorize_subscription"),
    path("api/v1/realtime/v2/revoke", realtime_v2.revoke, name="realtime_v2_revoke"),
    path("api/v1/realtime/v2/channel-registry", realtime_v2.channel_registry, name="realtime_v2_channel_registry"),
    path("api/v1/realtime/v2/health", realtime_v2.health, name="realtime_v2_health"),
    # Separate real-wallet boundary. Every real-value feature is disabled by
    # default and never falls back to the demo wallet.
    path("api/v1/", include("real_wallet.urls")),
    path("api/v1/", include("reference_data.urls")),
    path("api/v1/", include("trade.market_urls")),
    path("api/v1/trading/", include("apps.trading.api.urls")),
    path("api/v1/admin/", include("apps.trading.api.admin_urls")),
    path("api/v1/operator/surveillance/", include("apps.surveillance.urls")),
    path("api/v1/news", news_views.news_list_v1, name="news_v1"),
    path("api/v1/news/crypto", news_views.news_crypto_v1, name="news_crypto_v1"),
    path("api/v1/news/market", news_views.news_market_v1, name="news_market_v1"),
    path("api/v1/news/sources", news_views.news_sources_v1, name="news_sources_v1"),
    path("api/v1/news/archive", news_views.news_archive_v1, name="news_archive_v1"),
    path("api/v1/news/<str:article_id>", news_views.news_detail_v1, name="news_detail_v1"),
    path("api/v1/economic-calendar", news_views.economic_calendar_v1, name="economic_calendar_v1"),
    path("api/", include("api_trade.urls")),
    path("api/wallet/", include("wallet.urls")),
    path("api/notification/", include("notifications.urls")),
    path("api/payment/", include("payments.urls")),
    path("api/news/", include("news_app.urls")),
    path("api/admin/", include("users.admin_urls")),
    path("api/admin/", include("tickets.admin_urls")),
    path("api/trades/", include("trade.urls")),
    path("api/security/", include("security.urls")),
    path("api/bank_account/", include("bank_account_app.urls")),
    path("api/charts/", include("coinmarketcharts.urls")),
    # Portfolio
    path("api/portfolio/", include("portfolio.urls")),
    path("api/reporting/", include("reporting.urls")),
    path("api/", include("integrations.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
