import uuid

from django.db import models
from django.db.models import Q


class NewsArticle(models.Model):
    class Status(models.TextChoices):
        PUBLISHED = "PUBLISHED"
        UPDATED = "UPDATED"
        RETRACTED = "RETRACTED"

    article_id = models.CharField(max_length=128, primary_key=True)
    provider_id = models.CharField(max_length=64)
    provider_article_id = models.CharField(max_length=255)
    headline = models.CharField(max_length=512)
    summary = models.TextField(blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    canonical_url = models.URLField(max_length=1024, null=True, blank=True)
    published_at = models.DateTimeField()
    updated_at = models.DateTimeField(null=True, blank=True)
    retracted_at = models.DateTimeField(null=True, blank=True)
    importance = models.CharField(max_length=16, default="MEDIUM")
    affected_instruments = models.JSONField(default=list)
    affected_assets = models.JSONField(default=list)
    affected_currencies = models.JSONField(default=list)
    language = models.CharField(max_length=16, default="en")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PUBLISHED)

    class Meta:
        db_table = "news_articles"
        constraints = [
            models.UniqueConstraint(fields=["provider_id", "provider_article_id"], name="news_provider_article_unique"),
            models.UniqueConstraint(fields=["canonical_url"], condition=Q(canonical_url__isnull=False) & ~Q(canonical_url=""), name="news_canonical_url_unique"),
        ]
        indexes = [models.Index(fields=["status", "-published_at"])]


class EconomicCalendarEvent(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED"
        ACTIVE = "ACTIVE"
        RELEASED = "RELEASED"
        UPDATED = "UPDATED"
        CANCELLED = "CANCELLED"

    event_id = models.CharField(max_length=128, primary_key=True)
    provider_id = models.CharField(max_length=64)
    provider_event_id = models.CharField(max_length=255)
    title = models.CharField(max_length=512)
    country = models.CharField(max_length=64, blank=True)
    currency = models.CharField(max_length=16, blank=True)
    importance = models.CharField(max_length=16, default="MEDIUM")
    scheduled_at = models.DateTimeField()
    actual_at = models.DateTimeField(null=True, blank=True)
    previous_value = models.CharField(max_length=128, blank=True)
    forecast_value = models.CharField(max_length=128, blank=True)
    actual_value = models.CharField(max_length=128, blank=True)
    unit = models.CharField(max_length=32, blank=True)
    affected_instruments = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)

    class Meta:
        db_table = "economic_calendar_events"
        constraints = [models.UniqueConstraint(fields=["provider_id", "provider_event_id"], name="calendar_provider_event_unique")]
        indexes = [models.Index(fields=["status", "scheduled_at"])]


class NewsCalendarEventOutbox(models.Model):
    """Provider event committed atomically with its canonical projection."""

    sequence = models.BigAutoField(primary_key=True)
    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=64)
    event_version = models.PositiveSmallIntegerField(default=1)
    channel = models.CharField(max_length=255)
    source = models.CharField(max_length=64)
    data = models.JSONField(default=dict)
    occurred_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "news_calendar_event_outbox"
        indexes = [models.Index(fields=("next_attempt_at", "sequence"), condition=Q(published_at__isnull=True), name="news_cal_outbox_pending_idx")]
