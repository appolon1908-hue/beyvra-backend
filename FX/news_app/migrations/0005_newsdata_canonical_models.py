from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("news_app", "0004_consolidate_application_outbox")]
    operations = [
        migrations.AddField(model_name="newsarticle", name="content_preview", field=models.TextField(blank=True)),
        migrations.AddField(model_name="newsarticle", name="source_id", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="newsarticle", name="source_url", field=models.URLField(blank=True, max_length=1024, null=True)),
        migrations.AddField(model_name="newsarticle", name="image_url", field=models.URLField(blank=True, max_length=1024, null=True)),
        migrations.AddField(model_name="newsarticle", name="countries", field=models.JSONField(default=list)),
        migrations.AddField(model_name="newsarticle", name="categories", field=models.JSONField(default=list)),
        migrations.AddField(model_name="newsarticle", name="keywords", field=models.JSONField(default=list)),
        migrations.AddField(model_name="newsarticle", name="sentiment", field=models.CharField(blank=True, max_length=32)),
        migrations.AddField(model_name="newsarticle", name="received_at", field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now), preserve_default=False),
        migrations.AddField(model_name="newsarticle", name="provider_timestamp", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="newsarticle", name="delayed", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="newsarticle", name="raw_payload_hash", field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name="newsarticle", name="normalizer_version", field=models.CharField(default="newsdata-v1", max_length=32)),
        migrations.CreateModel(name="NewsSource", fields=[("source_id", models.CharField(max_length=255, primary_key=True, serialize=False)), ("name", models.CharField(max_length=255)), ("domain", models.CharField(blank=True, max_length=255)), ("url", models.URLField(blank=True, max_length=1024, null=True)), ("country", models.CharField(blank=True, max_length=16)), ("language", models.CharField(blank=True, max_length=16)), ("categories", models.JSONField(default=list)), ("provider_id", models.CharField(default="newsdata", max_length=64)), ("active", models.BooleanField(default=True)), ("updated_at", models.DateTimeField(auto_now=True))], options={"db_table":"news_sources"}),
        migrations.AddConstraint(model_name="newssource", constraint=models.UniqueConstraint(fields=("provider_id","source_id"), name="news_source_provider_unique")),
    ]
