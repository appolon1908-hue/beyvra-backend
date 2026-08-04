import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from real_wallet.webhooks import (
    WebhookSecurityError,
    decrypt_secret,
    encrypt_secret,
    signature_headers,
    validate_webhook_destination,
    verify_signature,
)


class WebhookSecurityTests(SimpleTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.key_file = Path(self.tempdir.name) / "master.key"
        self.key_file.write_bytes(b"k" * 32)

    def tearDown(self):
        self.tempdir.cleanup()

    @override_settings(REAL_WALLET_WEBHOOK_MASTER_KEY_FILE="")
    def test_missing_master_key_fails_closed(self):
        with self.assertRaises(WebhookSecurityError):
            encrypt_secret("synthetic")

    def test_secret_is_encrypted_and_round_trips(self):
        with override_settings(REAL_WALLET_WEBHOOK_MASTER_KEY_FILE=str(self.key_file)):
            nonce, ciphertext = encrypt_secret("synthetic-secret")
            self.assertNotEqual(ciphertext, b"synthetic-secret")
            self.assertEqual(decrypt_secret(nonce, ciphertext), "synthetic-secret")

    def test_signature_and_timestamp_validation(self):
        body = b'{"id":"evt_1"}'
        now = int(datetime.now(timezone.utc).timestamp())
        headers = signature_headers(timestamp=now, webhook_id="evt_1", raw_body=body, secret="secret", key_id="k1")
        self.assertTrue(verify_signature(timestamp=now, webhook_id="evt_1", raw_body=body, signature=headers["Webhook-Signature"], secret="secret"))
        self.assertFalse(verify_signature(timestamp=now, webhook_id="evt_1", raw_body=b"tampered", signature=headers["Webhook-Signature"], secret="secret"))

    @patch("real_wallet.webhooks.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.8", 443))])
    def test_ssrf_destination_is_rejected(self, _resolve):
        with self.assertRaises(WebhookSecurityError):
            validate_webhook_destination("https://example.invalid/callback")

    def test_webhook_requires_https(self):
        with self.assertRaises(WebhookSecurityError):
            validate_webhook_destination("http://example.com/callback")
