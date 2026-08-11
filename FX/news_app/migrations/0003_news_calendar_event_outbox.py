import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("news_app", "0002_rename_economic_ca_status_f0be0e_idx_economic_ca_status_21a137_idx_and_more")]
    operations = [
        migrations.AddConstraint(
            model_name="newsarticle",
            constraint=models.UniqueConstraint(condition=models.Q(("canonical_url__isnull", False), models.Q(("canonical_url", ""), _negated=True)), fields=("canonical_url",), name="news_canonical_url_unique"),
        ),
        migrations.CreateModel(
            name="NewsCalendarEventOutbox",
            fields=[
                ("sequence", models.BigAutoField(primary_key=True, serialize=False)),
                ("event_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("event_type", models.CharField(max_length=64)), ("event_version", models.PositiveSmallIntegerField(default=1)),
                ("channel", models.CharField(max_length=255)), ("source", models.CharField(max_length=64)),
                ("data", models.JSONField(default=dict)), ("occurred_at", models.DateTimeField()),
                ("published_at", models.DateTimeField(blank=True, null=True)), ("attempt_count", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(blank=True, null=True)), ("last_error_code", models.CharField(blank=True, max_length=64)),
            ],
            options={"db_table": "news_calendar_event_outbox"},
        ),
        migrations.AddIndex(model_name="newscalendareventoutbox", index=models.Index(condition=models.Q(("published_at__isnull", True)), fields=["next_attempt_at", "sequence"], name="news_cal_outbox_pending_idx")),
    ]
