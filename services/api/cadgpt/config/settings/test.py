"""Tests. Fast hashing, in-memory email, and tasks that run where they are called.

`CELERY_TASK_ALWAYS_EAGER` is deliberate: the test suite exercises the same task function
the worker runs, rather than a mock of it. The dispatch path itself is covered separately
by asserting what was enqueued.
"""

from __future__ import annotations

from cadgpt.config.settings.base import *

# At least 32 bytes: PyJWT warns below that for HMAC-SHA256, and a test key that
# trips a security warning trains everyone to ignore security warnings.
SECRET_KEY = "test-only-not-a-secret-but-long-enough-for-hmac-sha256"  # noqa: S105
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "ATOMIC_REQUESTS": False,
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False

REFRESH_COOKIE_SECURE = False

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Throttling would make test outcomes depend on how many tests ran before them.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {},
}

LOGGING = {"version": 1, "disable_existing_loggers": True, "handlers": {}, "root": {}}
