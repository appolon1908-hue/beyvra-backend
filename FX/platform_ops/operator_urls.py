from django.urls import path
from platform_ops.health.api import OperatorHealthView,OperatorDependenciesView
from platform_ops.slo.api import SlosView,ErrorBudgetsView
from platform_ops.capacity.api import CapacityView
from platform_ops.degraded_mode.api import ModeView
from platform_ops.kill_switch.api import KillSwitchListView,KillSwitchActivateView,KillSwitchRequestDeactivationView,KillSwitchApproveDeactivationView
from platform_ops.release.api import ReleaseView
from platform_ops.deployment.api import DeploymentView
from platform_ops.configuration.api import ConfigurationView
from platform_ops.feature_flags.api import FeatureFlagsView
from platform_ops.incidents.api import IncidentView,IncidentAcknowledgeView,IncidentResolveView
from platform_ops.reconciliation.api import ReconciliationView,ReconciliationRunView
from platform_ops.evidence.api import EvidenceView
urlpatterns=[
path("health",OperatorHealthView.as_view()),path("dependencies",OperatorDependenciesView.as_view()),path("slos",SlosView.as_view()),path("slos/<str:code>",SlosView.as_view()),path("error-budgets",ErrorBudgetsView.as_view()),
path("capacity",CapacityView.as_view()),path("capacity/<str:service_code>",CapacityView.as_view()),path("mode",ModeView.as_view()),
path("kill-switches",KillSwitchListView.as_view()),path("kill-switches/<str:code>/activate",KillSwitchActivateView.as_view()),path("kill-switches/<str:code>/request-deactivation",KillSwitchRequestDeactivationView.as_view()),path("kill-switches/<str:code>/approve-deactivation",KillSwitchApproveDeactivationView.as_view()),
path("release",ReleaseView.as_view()),path("release/<uuid:release_id>",ReleaseView.as_view()),path("release/<uuid:release_id>/evidence",EvidenceView.as_view()),path("deployments",DeploymentView.as_view()),path("configuration",ConfigurationView.as_view()),path("feature-flags",FeatureFlagsView.as_view()),
path("incidents",IncidentView.as_view()),path("incidents/<uuid:incident_id>",IncidentView.as_view()),path("incidents/<uuid:incident_id>/acknowledge",IncidentAcknowledgeView.as_view()),path("incidents/<uuid:incident_id>/resolve",IncidentResolveView.as_view()),
path("reconciliation",ReconciliationView.as_view()),path("reconciliation/run",ReconciliationRunView.as_view())]
