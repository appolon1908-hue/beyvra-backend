import os

os.environ.setdefault("SECRET_KEY", "isolated-test-only-django-secret-key")
os.environ.setdefault("ALLOWED_HOSTS", '["testserver","localhost","127.0.0.1"]')
os.environ.setdefault("CSRF_TRUSTED_ORIGINS", '["http://localhost","http://127.0.0.1"]')

from .settings import *  # noqa: F403

if os.getenv("DB_HOST"):
    DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": os.getenv("DB_NAME"), "USER": os.getenv("DB_USER"), "PASSWORD": os.getenv("DB_PASSWORD"), "HOST": os.getenv("DB_HOST"), "PORT": os.getenv("DB_PORT", "5432"), "TEST": {"NAME": os.getenv("TEST_DB_NAME", "test_codestra_ci")}}}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "test.sqlite3"}}  # noqa: F405

if os.getenv("TEST_POSTGRES") == "1":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ["DB_USER"],
            "PASSWORD": os.environ["DB_PASSWORD"],
            "HOST": os.environ["DB_HOST"],
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DEBUG = False
SECURE_SSL_REDIRECT = False
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405

# Synthetic test-only key material. Production settings remain fail-closed
# unless the corresponding protected secret or secret-file reference exists.
API_TOKEN_PEPPER = "isolated-test-only-api-token-pepper"
WEBHOOK_MASTER_KEY = "isolated-test-only-webhook-master-key"
