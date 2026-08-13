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
    content_preview = models.TextField(blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    source_id = models.CharField(max_length=255, blank=True)
    source_url = models.URLField(max_length=1024, null=True, blank=True)
    canonical_url = models.URLField(max_length=1024, null=True, blank=True)
    image_url = models.URLField(max_length=1024, null=True, blank=True)
    published_at = models.DateTimeField()
    updated_at = models.DateTimeField(null=True, blank=True)
    retracted_at = models.DateTimeField(null=True, blank=True)
    importance = models.CharField(max_length=16, default="MEDIUM")
    affected_instruments = models.JSONField(default=list)
    affected_assets = models.JSONField(default=list)
    affected_currencies = models.JSONField(default=list)
    countries = models.JSONField(default=list)
    categories = models.JSONField(default=list)
    keywords = models.JSONField(default=list)
    sentiment = models.CharField(max_length=32, blank=True)
    language = models.CharField(max_length=16, default="en")
    received_at = models.DateTimeField(auto_now_add=True)
    provider_timestamp = models.DateTimeField(null=True, blank=True)
    delayed = models.BooleanField(default=True)
    raw_payload_hash = models.CharField(max_length=64, blank=True)
    normalizer_version = models.CharField(max_length=32, default="newsdata-v1")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PUBLISHED)

    class Meta:
        db_table = "news_articles"
        constraints = [
            models.UniqueConstraint(fields=["provider_id", "provider_article_id"], name="news_provider_article_unique"),
            models.UniqueConstraint(fields=["canonical_url"], condition=Q(canonical_url__isnull=False) & ~Q(canonical_url=""), name="news_canonical_url_unique"),
        ]
        indexes = [models.Index(fields=["status", "-published_at"])]


class NewsSource(models.Model):
    source_id = models.CharField(max_length=255, primary_key=True)
    name = models.CharField(max_length=255)
    domain = models.CharField(max_length=255, blank=True)
    url = models.URLField(max_length=1024, null=True, blank=True)
    country = models.CharField(max_length=16, blank=True)
    language = models.CharField(max_length=16, blank=True)
    categories = models.JSONField(default=list)
    provider_id = models.CharField(max_length=64, default="newsdata")
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "news_sources"
        constraints = [models.UniqueConstraint(fields=["provider_id", "source_id"], name="news_source_provider_unique")]


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
