from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from notifications.serializers import WebhookSubscriptionSerializer


@override_settings(DEBUG=False)
class WebhookDestinationPolicyTests(SimpleTestCase):
    def validate_addresses(self, addresses):
        records = [(None, None, None, None, (address, 443)) for address in addresses]
        with patch('notifications.webhook_transport.socket.getaddrinfo', return_value=records):
            return WebhookSubscriptionSerializer().validate_url('https://webhook.example.test/events')

    def test_nonpublic_ipv6_and_mixed_answers_are_rejected(self):
        for address in ('::', '::1', 'fd00::1', 'fe80::1', 'ff02::1', '::ffff:127.0.0.1', '::ffff:169.254.169.254'):
            for addresses in ([address], ['93.184.216.34', address]):
                with self.subTest(addresses=addresses), self.assertRaises(ValidationError):
                    self.validate_addresses(addresses)

    def test_public_ipv6_and_ipv4_are_allowed(self):
        self.assertEqual(self.validate_addresses(['2606:4700:4700::1111', '93.184.216.34']), 'https://webhook.example.test/events')

    def test_empty_answer_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.validate_addresses([])

    def test_invalid_authority_is_rejected_before_dns(self):
        for url in ('https://user:password@example.test', 'https://[fe80::1%25eth0]/', 'https://example.test:bad', 'https://example.test/#fragment'):
            with self.subTest(url=url), patch('notifications.webhook_transport.socket.getaddrinfo') as resolve:
                with self.assertRaises(ValidationError):
                    WebhookSubscriptionSerializer().validate_url(url)
                resolve.assert_not_called()
