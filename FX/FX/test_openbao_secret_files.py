"""Runtime secret delivery regressions; all material below is invalid test data."""
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("secret_files_under_test", ROOT / 'FX/FX/secret_files.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SecretFileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "secret"
        self.path.write_text("invalid-local-fixture\n")
        self.path.chmod(0o400)

    def test_file_value_is_read_without_environment_materialization(self):
        with patch.dict(os.environ, {"EXAMPLE_FILE": str(self.path)}, clear=True):
            self.assertEqual(MODULE.environment_secret("EXAMPLE"), "invalid-local-fixture")
            self.assertNotIn("EXAMPLE", os.environ)

    def test_inline_and_file_conflict(self):
        with patch.dict(os.environ, {"EXAMPLE": "inline", "EXAMPLE_FILE": str(self.path)}, clear=True):
            with self.assertRaisesRegex(ValueError, "only one"):
                MODULE.environment_secret("EXAMPLE")

    def test_missing_file_has_no_inline_fallback(self):
        self.path.unlink()
        with patch.dict(os.environ, {"EXAMPLE_FILE": str(self.path)}, clear=True):
            with self.assertRaises(ValueError):
                MODULE.environment_secret("EXAMPLE", "fallback")

    def test_unsafe_files_are_rejected(self):
        for mode in (0o644, 0o440, 0o700):
            with self.subTest(mode=mode):
                self.path.chmod(mode)
                with self.assertRaises(ValueError):
                    MODULE.read_secret_file(str(self.path), "EXAMPLE")
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaises(ValueError):
            MODULE.read_secret_file(str(self.path), "EXAMPLE")

    def test_link_and_fifo_are_rejected(self):
        link = self.path.with_name("link")
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            MODULE.read_secret_file(str(link), "EXAMPLE")
        pipe = self.path.with_name("pipe")
        os.mkfifo(pipe, 0o600)
        with self.assertRaises(ValueError):
            MODULE.read_secret_file(str(pipe), "EXAMPLE")

    def test_empty_binary_and_oversized_values_are_rejected_without_contents(self):
        for data in (b" ", b"\xffinvalid-local-fixture", b"a\x00b", b"x" * 65537):
            self.path.chmod(0o600)
            self.path.write_bytes(data)
            with self.assertRaises(ValueError) as caught:
                MODULE.read_secret_file(str(self.path), "EXAMPLE")
            self.assertNotIn("invalid-local-fixture", str(caught.exception))

    def test_rotated_file_is_read_on_next_load(self):
        replacement = self.path.with_name("replacement")
        replacement.write_text("rotated-fixture")
        replacement.chmod(0o400)
        replacement.replace(self.path)
        self.assertEqual(MODULE.read_secret_file(str(self.path), "EXAMPLE"), "rotated-fixture")

    def test_inline_provider_credentials_keep_historic_trimming(self):
        with patch.dict(os.environ, {"POLYGON_API_KEY": "  certification-placeholder\n"}, clear=True):
            self.assertEqual(MODULE.environment_secret("POLYGON_API_KEY"), "certification-placeholder")

    def test_inline_password_values_preserve_whitespace(self):
        raw = "  database-password-with-spaces\n"
        with patch.dict(os.environ, {"DB_PASSWORD": raw}, clear=True):
            self.assertEqual(MODULE.environment_secret("DB_PASSWORD"), raw)

    def test_crypto_key_file_uses_hardened_loader_and_never_falls_back(self):
        if not os.getenv("DJANGO_SETTINGS_MODULE"):
            self.skipTest("Django settings are required for the integration consumer regression")
        from django.test import override_settings
        from integrations import crypto

        expected = hashlib.sha256(b"invalid-local-fixture").digest()
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": "", "DATA_ENCRYPTION_KEY_FILE": ""}):
            with override_settings(DATA_ENCRYPTION_KEY_FILE=str(self.path), DATA_ENCRYPTION_KEY=""):
                self.assertEqual(crypto.data_key(), expected)

            with override_settings(
                DATA_ENCRYPTION_KEY_FILE=str(self.path),
                DATA_ENCRYPTION_KEY="stale-inline-key",
            ):
                with self.assertRaisesRegex(RuntimeError, "only one source"):
                    crypto.data_key()

            self.path.chmod(0o644)
            with override_settings(DATA_ENCRYPTION_KEY_FILE=str(self.path), DATA_ENCRYPTION_KEY=""):
                with self.assertRaisesRegex(RuntimeError, "permissions"):
                    crypto.data_key()

    def test_contract_does_not_advertise_unused_password_reset_key(self):
        contract = json.loads((ROOT / "openbao-secret-consumer.v1.json").read_text(encoding="utf-8"))
        settings = {
            binding["setting"]
            for workload in contract["workloads"]
            for binding in workload["bindings"]
        }
        self.assertNotIn("PASSWORD_RESET_SIGNING_KEY", settings)


if __name__ == "__main__":
    unittest.main()
