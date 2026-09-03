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

# The production "auth" rate (10/min, base.py) is tuned against credential-stuffing, not
# against a Playwright suite that legitimately registers a fresh account per spec
# (`services/web/e2e/fixtures.ts`) plus the browser's own sign-in click on top of that --
# three "auth"-scoped requests per test, times however many spec files `make e2e` runs.
# Raised here only, in local/dev, where the accounts are throwaway harness fixtures, not
# a surface anyone attacks.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {"auth": "100/min", "upload": "60/hour", "check": "120/hour"},
}
