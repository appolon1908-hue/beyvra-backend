import uuid

from django.db import transaction
from django.utils import timezone

from apps.foundation.services import consume_once, enqueue_event

from .engine import SurveillanceEngine, evidence_hash
from .models import SurveillanceAudit, SurveillanceCase, SurveillanceCaseEvent, SurveillanceDeadLetter, SurveillanceEvent
from .observability import CASES, DEAD_LETTERS, EVENTS, HITS


def audit(*, tenant_ref, actor_ref, action, resource_type, resource_ref, reason, evidence=None):
    evidence = evidence or {}
    return SurveillanceAudit.objects.create(
        tenant_ref=tenant_ref,
        actor_ref=str(actor_ref),
        action=action,
        resource_type=resource_type,
        resource_ref=str(resource_ref),
        reason=reason,
        evidence_hash=evidence_hash(evidence),
        occurred_at=timezone.now(),
    )


@transaction.atomic
def persist_findings(*, tenant_ref, account_ref, instrument_id, findings, source_event_id=None, actor_ref="system", window_start=None, window_end=None):
    now = timezone.now()
    created = []
    for finding in findings:
        values = {
                "tenant_ref": tenant_ref,
                "account_ref": account_ref,
                "instrument_id": instrument_id,
                "event_type": finding.event_type,
                "severity": finding.severity,
                "detected_at": now,
                "window_start": window_start or now,
                "window_end": window_end or now,
                "rule_version": finding.rule_version,
                "policy_version": finding.policy_version,
                "score": finding.score,
                "evidence_hash": evidence_hash(finding.evidence_safe),
                "evidence_safe": finding.evidence_safe,
                "source_event_id": source_event_id,
                "rule_id": finding.rule_id,
        }
        if source_event_id is None:
            event, fresh = SurveillanceEvent.objects.create(**values), True
        else:
            event, fresh = SurveillanceEvent.objects.get_or_create(source_event_id=source_event_id, rule_id=finding.rule_id, defaults={key: value for key, value in values.items() if key not in {"source_event_id", "rule_id"}})
        if not fresh:
            continue
        created.append(event)
        EVENTS.labels(finding.event_type, finding.severity).inc()
        HITS.labels(finding.event_type, finding.severity).inc()
        audit(tenant_ref=tenant_ref, actor_ref=actor_ref, action="surveillance.event.generated", resource_type="surveillance_event", resource_ref=event.id, reason=finding.event_type, evidence={"rule_id": finding.rule_id, "rule_version": finding.rule_version})
        enqueue_event(aggregate_type="surveillance_event", aggregate_id=event.id, event_type="surveillance.alert.created.v1", payload={"event_id": str(event.id), "event_type": event.event_type, "severity": event.severity, "account_ref": account_ref, "instrument_id": instrument_id}, tenant_ref=tenant_ref)
        if finding.severity in {"HIGH", "CRITICAL"}:
            case = SurveillanceCase.objects.filter(tenant_ref=tenant_ref, account_ref=account_ref, case_type=finding.event_type, status__in=("OPEN", "IN_REVIEW", "ESCALATED", "RESTRICTED")).first()
            if case is None:
                case = SurveillanceCase.objects.create(tenant_ref=tenant_ref, account_ref=account_ref, case_type=finding.event_type, severity=finding.severity, opened_at=now, policy_version=finding.policy_version, evidence_hash=event.evidence_hash)
                SurveillanceCaseEvent.objects.create(case=case, event_type="CASE_OPENED", actor_ref="system", reason=finding.event_type, evidence_hash=event.evidence_hash, occurred_at=now)
                CASES.labels(finding.severity).inc()
                audit(tenant_ref=tenant_ref, actor_ref="system", action="surveillance.case.opened", resource_type="surveillance_case", resource_ref=case.id, reason=finding.event_type)
                enqueue_event(aggregate_type="surveillance_case", aggregate_id=case.id, event_type="surveillance.case.opened.v1", payload={"case_id": str(case.id), "case_type": case.case_type, "severity": case.severity, "account_ref": account_ref}, tenant_ref=tenant_ref)
            case.events.add(event)
    return created


def ingest_event(envelope):
    """Idempotently process a provider-neutral trading event."""
    payload = envelope.get("payload", {})
    tenant = str(envelope.get("tenant_ref") or payload.get("tenant_ref") or "")
    account = str(payload.get("account_ref") or "")
    instrument = str(payload.get("instrument") or payload.get("instrument_id") or "")

    def mutation():
        findings = SurveillanceEngine().evaluate_window(payload.get("window_events", []))
        persist_findings(tenant_ref=tenant, account_ref=account, instrument_id=instrument, findings=findings, source_event_id=uuid.UUID(str(envelope["event_id"])))

    try:
        return consume_once(envelope=envelope, consumer_name="surveillance-v1", mutation=mutation)
    except Exception as exc:
        now = timezone.now()
        try:
            event_id = uuid.UUID(str(envelope["event_id"]))
        except (ValueError, TypeError, KeyError):
            event_id = uuid.uuid5(uuid.NAMESPACE_URL, str(envelope.get("event_id", "missing")))
        SurveillanceDeadLetter.objects.update_or_create(event_id=event_id, event_type=str(envelope.get("event_type", "UNKNOWN"))[:128], defaults={"tenant_ref": tenant, "failure_category": type(exc).__name__[:64], "last_failed_at": now, "first_failed_at": now})
        DEAD_LETTERS.labels(type(exc).__name__[:64]).inc()
        raise
