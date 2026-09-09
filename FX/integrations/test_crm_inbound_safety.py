import hashlib
import hmac
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.foundation.models import IdempotencyRecord
from users.models import User
from .crypto import encrypt_secret
from .models import CRMConnection, DemoAccount, IntegrationAuditEvent, Organization
from .serializers import CRMConnectionSerializer


@override_settings(WEBHOOK_MASTER_KEY='crm-inbound-isolated-test-key')
class CRMInboundSafetyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.org = Organization.objects.create(name='Inbound tenant')
        owner = User.objects.create_user(email='crm-owner@example.test', password='test')
        self.secret = 'crm-signature-test-secret'
        ciphertext, nonce, version = encrypt_secret(self.secret)
        self.connection = CRMConnection.objects.create(
            organization=self.org, owner=owner, name='Synthetic CRM', is_active=True,
            endpoint='https://crm.example.test', secret_ciphertext=ciphertext,
            secret_nonce=nonce, secret_key_version=version,
        )
        self.path = f'/api/v1/integrations/crm/{self.connection.pk}/users'
        self.payload = {'external_user_id': 'external-1', 'first_name': 'Test', 'last_name': 'Person',
                        'email': 'inbound@example.test', 'phone': '+15555550900',
                        'organization_id': str(self.org.pk), 'consent': {'terms_accepted': True}}

    def send(self, payload=None, event_id='event-1', path=None, **headers):
        body = json.dumps(self.payload if payload is None else payload).encode()
        timestamp = str(int(timezone.now().timestamp()))
        signature = hmac.new(self.secret.encode(), timestamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
        return self.client.post(path or self.path, body, content_type='application/json', **{
            'HTTP_X_CODESTRA_TIMESTAMP': timestamp, 'HTTP_X_CODESTRA_EVENT_ID': event_id,
            'HTTP_X_CODESTRA_SIGNATURE_256': 'sha256=' + signature, **headers,
        })

    def test_replay_survives_cache_loss_and_url_alias(self):
        first = self.send()
        self.assertEqual(first.status_code, 201)
        cache.clear()
        replay = self.send(path=self.path + '/')
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(DemoAccount.objects.count(), 1)
        self.assertEqual(IntegrationAuditEvent.objects.filter(action='crm.inbound').count(), 1)
        self.assertEqual(self.send({**self.payload, 'email': 'changed@example.test'}).status_code, 409)

    def test_interrupted_audit_rolls_back_user_and_replay_claim(self):
        with patch('integrations.views.IntegrationAuditEvent.objects.create', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                self.send()
        self.assertFalse(User.objects.filter(email=self.payload['email']).exists())
        self.assertFalse(IdempotencyRecord.objects.filter(key='event-1').exists())
        self.assertEqual(self.send().status_code, 201)

    def test_invalid_payload_does_not_poison_retry(self):
        self.assertEqual(self.send({**self.payload, 'email': 'not-an-email'}).status_code, 400)
        self.assertFalse(IdempotencyRecord.objects.filter(key='event-1').exists())
        self.assertEqual(self.send().status_code, 201)

    def test_inactive_tenant_and_revoked_secret_are_rejected(self):
        self.org.is_active = False
        self.org.save(update_fields=['is_active'])
        self.assertEqual(self.send().status_code, 404)
        self.org.is_active = True
        self.org.save(update_fields=['is_active'])
        self.connection.secret_revoked_at = timezone.now()
        self.connection.save(update_fields=['secret_revoked_at'])
        self.assertEqual(self.send().status_code, 404)
        self.assertFalse(DemoAccount.objects.exists())

    def test_invalid_signature_and_event_identifier_fail_without_effects(self):
        for signature in ('sha256=é', 'sha256=' + '0' * 64):
            self.assertEqual(self.send(HTTP_X_CODESTRA_SIGNATURE_256=signature).status_code, 401)
        self.assertEqual(self.send(event_id='x' * 256).status_code, 400)
        self.assertEqual(self.send(HTTP_X_CODESTRA_TIMESTAMP='invalid').status_code, 401)
        self.assertFalse(IdempotencyRecord.objects.exists())


class CRMDestinationSafetyTests(SimpleTestCase):
    def test_nonpublic_ipv6_and_empty_dns_are_rejected(self):
        for addresses in ([], ['::1'], ['ff02::1'], ['::ffff:127.0.0.1'], ['93.184.216.34', 'fd00::1']):
            records = [(None, None, None, None, (address, 443)) for address in addresses]
            with self.subTest(addresses=addresses), patch('integrations.serializers.socket.getaddrinfo', return_value=records):
                with self.assertRaises(ValidationError):
                    CRMConnectionSerializer().validate_endpoint('https://crm.example.test')

    def test_public_ipv6_and_explicit_port_are_validated(self):
        with patch('integrations.serializers.socket.getaddrinfo', return_value=[(None, None, None, None, ('2606:4700:4700::1111', 8443))]) as resolver:
            url = 'https://crm.example.test:8443/events'
            self.assertEqual(CRMConnectionSerializer().validate_endpoint(url), url)
            self.assertEqual(resolver.call_args.args, ('crm.example.test', 8443))

    def test_credentials_and_malformed_port_rejected_before_dns(self):
        for url in ('https://user:secret@crm.example.test', 'https://crm.example.test:bad', 'https://[fe80::1%25eth0]'):
            with self.subTest(url=url), patch('integrations.serializers.socket.getaddrinfo') as resolver:
                with self.assertRaises(ValidationError):
                    CRMConnectionSerializer().validate_endpoint(url)
                resolver.assert_not_called()
