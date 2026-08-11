from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(name="NewsArticle", fields=[
            ("article_id", models.CharField(max_length=128, primary_key=True, serialize=False)),
            ("provider_id", models.CharField(max_length=64)), ("provider_article_id", models.CharField(max_length=255)),
            ("headline", models.CharField(max_length=512)), ("summary", models.TextField(blank=True)),
            ("publisher", models.CharField(blank=True, max_length=255)), ("canonical_url", models.URLField(blank=True, max_length=1024, null=True)),
            ("published_at", models.DateTimeField()), ("updated_at", models.DateTimeField(blank=True, null=True)),
            ("retracted_at", models.DateTimeField(blank=True, null=True)), ("importance", models.CharField(default="MEDIUM", max_length=16)),
            ("affected_instruments", models.JSONField(default=list)), ("affected_assets", models.JSONField(default=list)),
            ("affected_currencies", models.JSONField(default=list)), ("language", models.CharField(default="en", max_length=16)),
            ("status", models.CharField(choices=[("PUBLISHED", "Published"), ("UPDATED", "Updated"), ("RETRACTED", "Retracted")], default="PUBLISHED", max_length=16)),
        ], options={"db_table": "news_articles", "indexes": [models.Index(fields=["status", "-published_at"], name="news_articl_status_f3460a_idx")], "constraints": [models.UniqueConstraint(fields=("provider_id", "provider_article_id"), name="news_provider_article_unique")]}),
        migrations.CreateModel(name="EconomicCalendarEvent", fields=[
            ("event_id", models.CharField(max_length=128, primary_key=True, serialize=False)), ("provider_id", models.CharField(max_length=64)),
            ("provider_event_id", models.CharField(max_length=255)), ("title", models.CharField(max_length=512)),
            ("country", models.CharField(blank=True, max_length=64)), ("currency", models.CharField(blank=True, max_length=16)),
            ("importance", models.CharField(default="MEDIUM", max_length=16)), ("scheduled_at", models.DateTimeField()),
            ("actual_at", models.DateTimeField(blank=True, null=True)), ("previous_value", models.CharField(blank=True, max_length=128)),
            ("forecast_value", models.CharField(blank=True, max_length=128)), ("actual_value", models.CharField(blank=True, max_length=128)),
            ("unit", models.CharField(blank=True, max_length=32)), ("affected_instruments", models.JSONField(default=list)),
            ("status", models.CharField(choices=[("SCHEDULED", "Scheduled"), ("ACTIVE", "Active"), ("RELEASED", "Released"), ("UPDATED", "Updated"), ("CANCELLED", "Cancelled")], default="SCHEDULED", max_length=16)),
        ], options={"db_table": "economic_calendar_events", "indexes": [models.Index(fields=["status", "scheduled_at"], name="economic_ca_status_f0be0e_idx")], "constraints": [models.UniqueConstraint(fields=("provider_id", "provider_event_id"), name="calendar_provider_event_unique")]}),
    ]
