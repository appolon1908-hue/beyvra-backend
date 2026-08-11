import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0029_google_auth_foundation'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='email_verification_source',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='user',
            name='email_verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='PendingRegistration',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email_normalized', models.EmailField(max_length=254)),
                ('display_name', models.CharField(blank=True, max_length=120)),
                ('password_hash', models.CharField(max_length=128)),
                ('status', models.CharField(choices=[('pending_email_verification', 'Pending email verification'), ('completed', 'Completed'), ('expired', 'Expired')], default='pending_email_verification', max_length=32)),
                ('locale', models.CharField(default='en', max_length=16)),
                ('legal_confirmation', models.BooleanField(default=False)),
                ('legal_document_versions', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('request_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('request_user_agent', models.TextField(blank=True)),
                ('activated_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pending_registrations', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='EmailVerificationChallenge',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email_normalized', models.EmailField(max_length=254)),
                ('purpose', models.CharField(choices=[('registration', 'Registration'), ('email_change', 'Email change'), ('account_recovery', 'Account recovery')], default='registration', max_length=32)),
                ('otp_hash', models.CharField(max_length=255)),
                ('status', models.CharField(choices=[('active', 'Active'), ('consumed', 'Consumed'), ('invalidated', 'Invalidated'), ('locked', 'Locked')], default='active', max_length=16)),
                ('attempt_count', models.PositiveSmallIntegerField(default=0)),
                ('max_attempts', models.PositiveSmallIntegerField(default=5)),
                ('send_count', models.PositiveSmallIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                ('invalidated_at', models.DateTimeField(blank=True, null=True)),
                ('last_attempt_at', models.DateTimeField(blank=True, null=True)),
                ('last_sent_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='email_verification_challenges', to=settings.AUTH_USER_MODEL)),
                ('registration', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='challenges', to='users.pendingregistration')),
            ],
        ),
        migrations.CreateModel(
            name='TransactionalEmailOutbox',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('event_type', models.CharField(max_length=64)),
                ('recipient_email', models.EmailField(max_length=254)),
                ('template_key', models.CharField(max_length=64)),
                ('template_version', models.CharField(default='1', max_length=32)),
                ('locale', models.CharField(default='en', max_length=16)),
                ('payload', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('sent', 'Sent'), ('failed', 'Failed'), ('dead_letter', 'Dead letter')], default='pending', max_length=16)),
                ('attempt_count', models.PositiveSmallIntegerField(default=0)),
                ('next_attempt_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('provider_message_id', models.CharField(blank=True, max_length=255)),
                ('last_error_code', models.CharField(blank=True, max_length=64)),
                ('idempotency_key', models.CharField(max_length=255, unique=True)),
            ],
            options={
                'indexes': [models.Index(fields=['status', 'next_attempt_at'], name='email_outbox_status_next_idx')],
            },
        ),
        migrations.AddIndex(
            model_name='pendingregistration',
            index=models.Index(fields=['email_normalized', 'status'], name='pending_reg_email_status_idx'),
        ),
        migrations.AddIndex(
            model_name='emailverificationchallenge',
            index=models.Index(fields=['email_normalized', 'purpose', 'status'], name='email_challenge_lookup_idx'),
        ),
    ]
