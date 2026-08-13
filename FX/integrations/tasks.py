from celery import shared_task
from django.db import transaction

from users.models import User
from .models import DemoAccount, DemoLedgerEntry, ExternalIdentity, UserImport
from .services import emit_crm_event


@shared_task
def process_user_import(import_id):
    job = UserImport.objects.get(id=import_id)
    if job.status != "COMMITTED":
        return
    job.status = "PROCESSING"
    job.save(update_fields=["status", "updated_at"])
    for row in job.rows.filter(status="VALID").order_by("row_number"):
        try:
            with transaction.atomic():
                data = row.data
                user = User.objects.create_user(email=data["email"], password=None, first_name=data["first_name"], last_name=data["last_name"], phone_number=data["phone"], preferred_language=data.get("locale", "en"), country_iso_code=data.get("country", ""), verification_status="CHANGE_PASSWORD", email_verified=False)
                user.set_unusable_password(); user.save(update_fields=["password", "verification_status", "email_verified", "updated_at"])
                ExternalIdentity.objects.create(organization=job.organization, user=user, external_user_id=data["external_user_id"], source=data.get("source", "bulk_import"))
                account = DemoAccount.objects.create(user=user, organization=job.organization)
                DemoLedgerEntry.objects.create(account=account, reference=f"import:{job.id}:{row.row_number}")
                emit_crm_event(organization=job.organization, event_type="user.created", data={"user_id": str(user.id), "demo_account_id": str(account.id)}, correlation_id=user.id)
                row.user = user; row.status = "CREATED"; row.save(update_fields=["user", "status"])
        except Exception:
            row.status = "ERROR"; row.errors = ["row could not be imported"]; row.save(update_fields=["status", "errors"])
    job.status = "COMPLETED"; job.save(update_fields=["status", "updated_at"])
