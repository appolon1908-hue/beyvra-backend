import csv
import io
import json
from datetime import timedelta

from celery import shared_task
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from .artifacts import write_private_artifact
from .models import (
    AuditEvent,
    Notification,
    PrivacyExportJob,
    ReportJob,
    SecurityEvent,
    SupportCase,
    SupportCaseEvent,
    TransactionHistoryEntry,
)
from .services import csv_safe


REPORT_FIELDS = (
    "entry_id",
    "type",
    "asset",
    "amount",
    "fee",
    "status",
    "occurred_at",
    "settled_at",
    "source_ref",
    "simulation",
    "version",
)


@shared_task(name="operations.generate_report_artifact")
def generate_report_artifact(job_id):
    with transaction.atomic():
        job = ReportJob.objects.select_for_update().select_related("account").get(
            job_id=job_id
        )
        if job.status == "COMPLETED":
            return "COMPLETED"
        if job.status not in {"QUEUED", "FAILED"}:
            return job.status
        if not job.reconciliation_passed:
            job.status = "FAILED"
            job.save(update_fields=("status",))
            return "FAILED"
        job.status = "RUNNING"
        job.save(update_fields=("status",))

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=REPORT_FIELDS)
    writer.writeheader()
    entries = TransactionHistoryEntry.objects.filter(
        tenant_id=job.tenant_id, account=job.account
    ).order_by("occurred_at", "entry_id")
    if job.report_type in {"TRADE", "FEE"}:
        entries = entries.filter(type=job.report_type)
    for entry in entries.iterator():
        row = {
            field: getattr(entry, field) if field != "entry_id" else entry.entry_id
            for field in REPORT_FIELDS
        }
        writer.writerow({field: csv_safe(value) for field, value in row.items()})
    reference = write_private_artifact(
        namespace="reports", suffix="csv", content=output.getvalue().encode("utf-8")
    )
    now = timezone.now()
    with transaction.atomic():
        job = ReportJob.objects.select_for_update().get(job_id=job_id)
        job.status = "COMPLETED"
        job.completed_at = now
        job.expires_at = now + timedelta(hours=24)
        job.artifact_ref = reference
        job.save(
            update_fields=("status", "completed_at", "expires_at", "artifact_ref")
        )
        AuditEvent.objects.create(
            tenant_id=job.tenant_id,
            actor=job.account,
            action="REPORT_EXPORTED",
            target=str(job.job_id),
        )
    return "COMPLETED"


@shared_task(name="operations.generate_privacy_export")
def generate_privacy_export(job_id):
    with transaction.atomic():
        job = PrivacyExportJob.objects.select_for_update().select_related("account").get(
            job_id=job_id
        )
        if job.status == "COMPLETED":
            return "COMPLETED"
        if job.status not in {"QUEUED", "FAILED"}:
            return job.status
        job.status = "RUNNING"
        job.save(update_fields=("status",))

    account = job.account
    tenant_filter = {"tenant_id": job.tenant_id, "account": account}
    cases = SupportCase.objects.filter(**tenant_filter).order_by("created_at")
    case_ids = list(cases.values_list("case_id", flat=True))
    payload = {
        "policy_version": job.policy_version,
        "generated_at": timezone.now(),
        "profile": {
            "account_ref": str(account.pk),
            "email": account.email,
            "first_name": account.first_name,
            "last_name": account.last_name,
            "phone_number": account.phone_number,
        },
        "transactions": list(
            TransactionHistoryEntry.objects.filter(**tenant_filter).values(
                *REPORT_FIELDS
            )
        ),
        "support_cases": list(
            cases.values(
                "case_id",
                "category",
                "priority",
                "status",
                "created_at",
                "updated_at",
                "resolved_at",
                "safe_summary",
            )
        ),
        "support_messages": list(
            SupportCaseEvent.objects.filter(
                case_id__in=case_ids,
                visibility="CUSTOMER_VISIBLE_MESSAGE",
                **tenant_filter,
            ).values("event_id", "case_id", "event_type", "body_safe", "created_at")
        ),
        "security_events": list(
            SecurityEvent.objects.filter(**tenant_filter).values(
                "event_id", "event_type", "occurred_at", "resolved"
            )
        ),
        "notifications": list(
            Notification.objects.filter(**tenant_filter).values(
                "notification_id",
                "type",
                "category",
                "severity",
                "channel",
                "status",
                "created_at",
                "sent_at",
                "delivered_at",
                "read_at",
            )
        ),
    }
    content = json.dumps(payload, cls=DjangoJSONEncoder, sort_keys=True).encode("utf-8")
    reference = write_private_artifact(
        namespace="privacy", suffix="json", content=content
    )
    now = timezone.now()
    with transaction.atomic():
        job = PrivacyExportJob.objects.select_for_update().get(job_id=job_id)
        job.status = "COMPLETED"
        job.completed_at = now
        job.expires_at = now + timedelta(hours=24)
        job.artifact_ref = reference
        job.save(
            update_fields=("status", "completed_at", "expires_at", "artifact_ref")
        )
        AuditEvent.objects.create(
            tenant_id=job.tenant_id,
            actor=job.account,
            action="PRIVACY_EXPORT_GENERATED",
            target=str(job.job_id),
        )
    return "COMPLETED"
