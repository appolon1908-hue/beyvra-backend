from django.utils import timezone
from .invariants import summarize
from .models import FullStackReconciliationRun
def record_run(*,candidate_sha,policy_version,results,release_id=None):
    report=summarize(results)
    return FullStackReconciliationRun.objects.create(release_id=release_id,state=report["state"],checks=report["checks"],violations=report["violations"],candidate_sha=candidate_sha,policy_version=policy_version,completed_at=timezone.now())
