from django.urls import path
from .admin_api import CaseCollectionView, CaseEventView, OverrideApprovalView, OverrideCollectionView, RestrictionCollectionView
urlpatterns=[path("cases",CaseCollectionView.as_view()),path("cases/<uuid:case_id>/events",CaseEventView.as_view()),path("restrictions",RestrictionCollectionView.as_view()),path("overrides",OverrideCollectionView.as_view()),path("overrides/<uuid:override_id>/approve",OverrideApprovalView.as_view())]
