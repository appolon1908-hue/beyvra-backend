"""Versioned AES-GCM envelope encryption for integration credentials."""
import base64
import hashlib
import hmac
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def _read_key(path_setting, env_setting, fallback=None):
    path = getattr(settings, path_setting, "")
    if path:
        try:
            value = open(path, "rb").read().strip()
            if value:
                return value
        except OSError:
            pass
    value = os.getenv(env_setting, "")
    if value:
        return value.encode()
    return fallback


def _key(path_setting, env_setting):
    value = _read_key(path_setting, env_setting)
    if not value:
        raise RuntimeError(f"Missing protected key material for {env_setting}")
    # Accept base64-encoded 32-byte keys or derive a fixed-width key from a
    # protected secret-file value. The key is never persisted in the DB.
    try:
        decoded = base64.urlsafe_b64decode(value + b"=" * (-len(value) % 4))
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(value).digest()


def webhook_key():
    return _key("WEBHOOK_MASTER_KEY_FILE", "WEBHOOK_MASTER_KEY")


def data_key():
    return _key("DATA_ENCRYPTION_KEY_FILE", "DATA_ENCRYPTION_KEY")


def token_pepper():
    return _key("API_TOKEN_PEPPER_FILE", "API_TOKEN_PEPPER")


def encrypt(value, *, key_version="v1", key=None):
    nonce = os.urandom(12)
    ciphertext = AESGCM(key or data_key()).encrypt(nonce, value.encode(), key_version.encode())
    return base64.urlsafe_b64encode(ciphertext).decode(), base64.urlsafe_b64encode(nonce).decode(), key_version


def decrypt(ciphertext, nonce, *, key_version="v1", key=None):
    raw = base64.urlsafe_b64decode(ciphertext.encode())
    iv = base64.urlsafe_b64decode(nonce.encode())
    return AESGCM(key or data_key()).decrypt(iv, raw, key_version.encode()).decode()


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def token_digest(raw):
    return hmac.new(token_pepper(), raw.encode(), hashlib.sha256).hexdigest()


def encrypt_secret(value):
    return encrypt(value, key=webhook_key())


def decrypt_secret(value, nonce=None, key_version="v1"):
    # Legacy compatibility: old Fernet values are read only until the
    # expand/contract migration has re-encrypted them.
    if nonce:
        return decrypt(value, nonce, key_version=key_version, key=webhook_key())
    try:
        from cryptography.fernet import Fernet, InvalidToken
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
        return Fernet(key).decrypt(value.encode()).decode()
    except Exception:
        return value
