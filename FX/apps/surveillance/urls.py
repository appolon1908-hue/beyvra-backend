from django.urls import path

from .api import ApproveRestriction, AssignCase, CaseDetail, CaseList, EscalateCase, EventDetail, EventList, RemoveRestriction, ResolveCase, RestrictionList, RuleList

urlpatterns = [
    path("events", EventList.as_view()),
    path("events/<uuid:event_id>", EventDetail.as_view()),
    path("cases", CaseList.as_view()),
    path("cases/<uuid:case_id>", CaseDetail.as_view()),
    path("cases/<uuid:case_id>/assign", AssignCase.as_view()),
    path("cases/<uuid:case_id>/escalate", EscalateCase.as_view()),
    path("cases/<uuid:case_id>/resolve", ResolveCase.as_view()),
    path("restrictions", RestrictionList.as_view()),
    path("restrictions/<uuid:restriction_id>/approve", ApproveRestriction.as_view()),
    path("restrictions/<uuid:restriction_id>/remove", RemoveRestriction.as_view()),
    path("rules", RuleList.as_view()),
]
