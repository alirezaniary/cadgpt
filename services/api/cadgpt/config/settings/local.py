"""Development. Loud errors, no TLS assumptions, real Postgres and real Redis."""

from __future__ import annotations

from cadgpt.config.settings.base import *
from cadgpt.config.settings.base import env

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "api"]  # noqa: S104

# The SPA runs on its own origin in development, so the refresh cookie has to cross it.
REFRESH_COOKIE_SECURE = False
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
