"""Asynchronous real-wallet workers.

Workers operate only on persisted inbox/receipt rows. They never call a
custody or chain provider while an application request transaction is open.
Provider adapters are injected by the deployment and default to fail-closed.
"""

from celery import shared_task

from integrations.models import Organization

from .models import ProviderWebhookReceipt
from .provider_webhooks import mark_provider_webhook_processed, mark_provider_webhook_retry
from .reconciliation import run_balance_reconciliation


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def process_provider_webhook_receipt(self, receipt_id):
    receipt = ProviderWebhookReceipt.objects.select_related("connection").filter(pk=receipt_id).first()
    if receipt is None or receipt.status == "PROCESSED":
        return {"status": "ignored", "receipt_id": str(receipt_id)}
    try:
        if receipt.connection.status != "ACTIVE":
            raise RuntimeError("provider connection is not active")
        mark_provider_webhook_processed(receipt.id)
        return {"status": "processed", "receipt_id": str(receipt.id)}
    except Exception as exc:
        mark_provider_webhook_retry(receipt.id, str(exc))
        raise self.retry(exc=exc)


@shared_task
def run_provider_balance_reconciliation(tenant_id, external_balances):
    tenant = Organization.objects.get(pk=tenant_id)
    return str(run_balance_reconciliation(tenant=tenant, external_balances=external_balances).id)
