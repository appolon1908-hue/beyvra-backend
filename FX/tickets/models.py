import uuid
from enum import Enum

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


class TicketMessages(Enum):
    TICKET_NOT_FOUND = "Ticket not found."
    TICKET_DELETED_SUCCESS = "Ticket deleted successfully."
    TICKET_BANNED_SUCCESS = "Ticket banned successfully."
    TICKET_ALREADY_BANNED = "Ticket is already banned."
    TICKET_UPDATED_SUCCESS = "Ticket updated successfully."
    TICKET_ALREADY_UNBANNED = "Ticket is already unbanned."
    TICKET_UNBANNED_SUCCESS = "Ticket unbanned successfully."


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
