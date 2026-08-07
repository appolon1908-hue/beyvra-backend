import uuid

from django.db import migrations


def forwards(apps, _schema_editor):
    Legacy = apps.get_model("news_app", "NewsCalendarEventOutbox")
    Outbox = apps.get_model("foundation", "OutboxEvent")
    for row in Legacy.objects.all().iterator():
        data = row.data or {}
        aggregate_id = data.get("article_id") or data.get("event_id") or str(row.event_id)
        Outbox.objects.create(
            event_id=row.event_id, aggregate_type="news_article" if row.event_type.startswith("news.") else "economic_event",
            aggregate_id=aggregate_id, event_type=row.event_type, schema_version=row.event_version,
            payload={"channel": row.channel, "source": row.source, "data": data}, correlation_id=uuid.uuid4(),
            tenant_ref="public", occurred_at=row.occurred_at, created_at=row.occurred_at, published_at=row.published_at,
            attempt_count=row.attempt_count, next_attempt_at=row.next_attempt_at, last_error=row.last_error_code,
            state="PUBLISHED" if row.published_at else "PENDING",
        )


def backwards(apps, _schema_editor):
    Legacy = apps.get_model("news_app", "NewsCalendarEventOutbox")
    Outbox = apps.get_model("foundation", "OutboxEvent")
    for row in Outbox.objects.filter(
        aggregate_type__in=("news_article", "economic_event")
    ).iterator():
        payload = row.payload or {}
        Legacy.objects.update_or_create(
            event_id=row.event_id,
            defaults={
                "event_type": row.event_type,
                "event_version": row.schema_version,
                "channel": payload.get("channel", "news.market"),
                "source": payload.get("source", "application"),
                "data": payload.get("data", {}),
                "occurred_at": row.occurred_at,
                "published_at": row.published_at,
                "attempt_count": row.attempt_count,
                "next_attempt_at": row.next_attempt_at,
                "last_error_code": row.last_error,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("foundation", "0001_initial"), ("news_app", "0003_news_calendar_event_outbox")]
    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.DeleteModel(name="NewsCalendarEventOutbox"),
    ]
