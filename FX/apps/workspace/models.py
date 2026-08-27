import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from integrations.models import Organization


class Watchlist(models.Model):
    """Tenant-scoped presentation state; never a trading or pricing authority."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="workspace_watchlists",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_watchlists",
    )
    name = models.CharField(max_length=80)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_default", "created_at", "id")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "organization",
                "user",
                name="workspace_watchlist_name_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "user"),
                condition=models.Q(is_default=True),
                name="workspace_one_default_watchlist",
            ),
        ]
        indexes = [
            models.Index(
                fields=("organization", "user", "created_at"),
                name="workspace_watchlist_owner_idx",
            )
        ]


class WatchlistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    watchlist = models.ForeignKey(
        Watchlist,
        on_delete=models.CASCADE,
        related_name="items",
    )
    instrument_id = models.CharField(max_length=64)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("sort_order", "created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("watchlist", "instrument_id"),
                name="workspace_watchlist_instrument_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("watchlist", "sort_order"),
                name="workspace_watchlist_order_idx",
            )
        ]
