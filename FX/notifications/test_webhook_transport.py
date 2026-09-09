import os
import socket
import ssl
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings

from notifications.serializers import WebhookSubscriptionSerializer
from notifications.webhook_transport import UnsafeWebhookDestination, post_webhook


def answers(*addresses):
    return [(None, None, None, None, (address, 443)) for address in addresses]


@override_settings(DEBUG=False)
class WebhookTransportTests(SimpleTestCase):
    def test_dns_change_after_registration_is_rejected_at_delivery(self):
        url = 'https://receiver.example.test/events'
        with patch('notifications.webhook_transport.socket.getaddrinfo', side_effect=[answers('93.184.216.34'), answers('::1')]), patch('notifications.webhook_transport.urllib3.HTTPSConnectionPool') as pool:
            WebhookSubscriptionSerializer().validate_url(url)
            with self.assertRaises(UnsafeWebhookDestination):
                post_webhook(url, data=b'{}', headers={}, timeout=1)
            pool.assert_not_called()

    def test_all_dns_answers_are_checked_before_connecting(self):
        for addresses in (['93.184.216.34', 'fd00::1'], ['::ffff:127.0.0.1'], []):
            with self.subTest(addresses=addresses), patch('notifications.webhook_transport.socket.getaddrinfo', return_value=answers(*addresses)), patch('notifications.webhook_transport.urllib3.HTTPSConnectionPool') as pool:
                with self.assertRaises(UnsafeWebhookDestination):
                    post_webhook('https://receiver.example.test/', data=b'{}', headers={}, timeout=1)
                pool.assert_not_called()

    def test_public_ip_is_pinned_with_original_tls_identity_and_no_redirects(self):
        for address in ('93.184.216.34', '2606:4700:4700::1111'):
            with self.subTest(address=address), patch.dict(os.environ, {'HTTPS_PROXY': 'http://127.0.0.1:9999'}), patch('notifications.webhook_transport.socket.getaddrinfo', side_effect=[answers(address), answers('127.0.0.1')]) as dns, patch('notifications.webhook_transport.urllib3.HTTPSConnectionPool') as pool:
                response = pool.return_value.urlopen.return_value
                response.status = 302
                result = post_webhook('https://receiver.example.test:8443/events?x=1', data=b'{}', headers={'Host': 'wrong'}, timeout=2)
                self.assertEqual(result.status_code, 302)
                self.assertEqual(dns.call_count, 1)
                options = pool.call_args.kwargs
                self.assertEqual(options['host'], address)
                self.assertEqual(options['server_hostname'], 'receiver.example.test')
                self.assertEqual(options['assert_hostname'], 'receiver.example.test')
                self.assertEqual(options['cert_reqs'], 'CERT_REQUIRED')
                call = pool.return_value.urlopen.call_args
                self.assertEqual(call.args, ('POST', '/events?x=1'))
                self.assertEqual(call.kwargs['headers']['Host'], 'receiver.example.test:8443')
                self.assertFalse(call.kwargs['redirect'])
                self.assertFalse(call.kwargs['retries'])
                self.assertFalse(call.kwargs['preload_content'])
                response.close.assert_called_once()
                pool.return_value.close.assert_called_once()


@override_settings(DEBUG=False)
class WebhookTLSIntegrationTests(SimpleTestCase):
    def test_pinned_socket_preserves_sni_and_rejects_wrong_certificate_hostname(self):
        received = []
        server_names = []

        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.headers['Host'], self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory() as directory:
            cert = str(Path(directory) / 'cert.pem')
            key = str(Path(directory) / 'key.pem')
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'receiver.example.test')])
            now = datetime.now(timezone.utc)
            certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                           .public_key(private_key.public_key()).serial_number(x509.random_serial_number())
                           .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
                           .add_extension(x509.SubjectAlternativeName([x509.DNSName('receiver.example.test')]), critical=False)
                           .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                           .sign(private_key, hashes.SHA256()))
            Path(cert).write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
            Path(key).write_bytes(private_key.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
            server = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            context.set_servername_callback(lambda sock, name, ctx: server_names.append(name))
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            def local_socket(address, *args, **kwargs):
                self.assertEqual(address, ('93.184.216.34', 443))
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect(('127.0.0.1', server.server_port))
                return sock

            try:
                with patch('notifications.webhook_transport.socket.getaddrinfo', return_value=answers('93.184.216.34')), patch('urllib3.util.connection.create_connection', side_effect=local_socket), patch('notifications.webhook_transport.requests.certs.where', return_value=cert):
                    result = post_webhook('https://receiver.example.test/events', data=b'payload', headers={}, timeout=2)
                    self.assertEqual(result.status_code, 204)
                    with self.assertRaises(requests.ConnectionError):
                        post_webhook('https://wrong.example.test/events', data=b'private', headers={}, timeout=2)
                self.assertEqual(received, [('receiver.example.test', b'payload')])
                self.assertEqual(server_names, ['receiver.example.test', 'wrong.example.test'])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
