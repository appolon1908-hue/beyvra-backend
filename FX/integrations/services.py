from notifications.services import emit_notification

from .models import CRMConnection


def emit_crm_event(*, organization, event_type, data, correlation_id):
    """Use the existing durable notification/webhook queue for CRM delivery."""
    for connection in CRMConnection.objects.filter(organization=organization, is_active=True):
        allowed = connection.event_categories or []
        if allowed and event_type not in allowed:
            continue
        emit_notification(
            user_id=connection.owner_id,
            title=event_type,
            message=event_type,
            category=event_type,
            payload={"event_id": str(correlation_id), "event_type": event_type, "event_version": "1.0", "organization_id": str(organization.id), "correlation_id": str(correlation_id), "data": data},
            force=True,
        )
