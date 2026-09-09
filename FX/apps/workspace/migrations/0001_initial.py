import uuid

import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("integrations", "0002_credential_encryption"),
    ]

    operations = [
        migrations.CreateModel(
            name="Watchlist",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=80)),
                ("is_default", models.BooleanField(default=False)),
                ("version", models.PositiveBigIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workspace_watchlists",
                        to="integrations.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workspace_watchlists",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-is_default", "created_at", "id")},
        ),
        migrations.CreateModel(
            name="WatchlistItem",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("instrument_id", models.CharField(max_length=64)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "watchlist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="workspace.watchlist",
                    ),
                ),
            ],
            options={"ordering": ("sort_order", "created_at", "id")},
        ),
        migrations.AddConstraint(
            model_name="watchlist",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                models.F("organization"),
                models.F("user"),
                name="workspace_watchlist_name_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="watchlist",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)),
                fields=("organization", "user"),
                name="workspace_one_default_watchlist",
            ),
        ),
        migrations.AddConstraint(
            model_name="watchlist",
            constraint=models.CheckConstraint(
                condition=models.Q(("version__gte", 1)),
                name="workspace_watchlist_version_positive",
            ),
        ),
        migrations.AddIndex(
            model_name="watchlist",
            index=models.Index(
                fields=["organization", "user", "created_at"],
                name="workspace_watchlist_owner_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="watchlistitem",
            constraint=models.UniqueConstraint(
                fields=("watchlist", "instrument_id"),
                name="workspace_watchlist_instrument_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="watchlistitem",
            index=models.Index(
                fields=["watchlist", "sort_order"],
                name="workspace_watchlist_order_idx",
            ),
        ),
    ]
