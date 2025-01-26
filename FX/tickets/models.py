import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _
from users.models import User


class TicketStatus(models.TextChoices):
    PENDING = "Pending", _("Pending")
    IN_PROGRESS = "In_Progress", _("In Progress")
    ESCALATED = "Escalated", _("Escalated")
    RESOLVED = "Resolved", _("Resolved")
    CANCELLED = "Cancelled", _("Cancelled")
    REOPENED = "Reopened", _("Reopened")


class SupportTicket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.CharField(max_length=255, null=True, blank=True)
    message = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=TicketStatus.choices, default=TicketStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assigned_admin = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tickets"
    )
