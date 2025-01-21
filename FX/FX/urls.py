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

urlpatterns = [
    path("", include("django_prometheus.urls")),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/frontendadmin/90210/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
    path("api/user/", include("users.urls")),
    # path("api/", include("api_trade.urls")),
    path("api/wallet/", include("wallet.urls")),
    path("api/notification/", include("notifications.urls")),
    path("api/payment/", include("payments.urls")),
    path("api/news/", include("news_app.urls")),
    path("api/admin/", include("users.admin_urls")),
    path("api/trades/", include("trade.urls")),
    path("api/security/", include("security.urls")),
    path("api/bank_account/", include("bank_account_app.urls")),
    path("api/charts/", include("coinmarketcharts.urls")),

    # Dashboard metrics
    path("api/reporting/", include("reporting.urls")),
    
    # Portfolio
    path("api/portfolio/", include("portfolio.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
