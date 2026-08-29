from django.urls import path
from .views import ControlPlaneContextView, CRMConnectionDetailView, CRMConnectionListView, CRMInboundUserView, CSVTemplateView, ImportCancelView, ImportCommitView, ImportDetailView, ImportRowsView, PublicIntakeView, ServiceTokenActionView, ServiceTokenListView, TenantContextView, UserCreateView, UserImportView

urlpatterns = [
    path("v1/public/intake", PublicIntakeView.as_view(), name="public_intake"),
    path("v1/public/intake/", PublicIntakeView.as_view()),
    path("v1/control-plane/context", ControlPlaneContextView.as_view()),
    path("v1/tenant/context", TenantContextView.as_view()),
    path("v1/users", UserCreateView.as_view()),
    path("v1/users/", UserCreateView.as_view()),
    path("v1/users/imports", UserImportView.as_view()),
    path("v1/users/imports/", UserImportView.as_view()),
    path("v1/users/imports/template", CSVTemplateView.as_view()),
    path("v1/users/imports/<uuid:import_id>", ImportDetailView.as_view()),
    path("v1/users/imports/<uuid:import_id>/rows", ImportRowsView.as_view()),
    path("v1/users/imports/<uuid:import_id>/commit", ImportCommitView.as_view()),
    path("v1/users/imports/<uuid:import_id>/cancel", ImportCancelView.as_view()),
    path("v1/integrations/crm/<uuid:connection_id>/users", CRMInboundUserView.as_view()),
    path("v1/integrations/crm/<uuid:connection_id>/users/", CRMInboundUserView.as_view()),
    path("v1/integrations/crm/connections", CRMConnectionListView.as_view()),
    path("v1/integrations/crm/connections/<uuid:connection_id>", CRMConnectionDetailView.as_view()),
    path("v1/integrations/service-tokens", ServiceTokenListView.as_view()),
    path("v1/integrations/service-tokens/<uuid:token_id>", ServiceTokenActionView.as_view()),
]
