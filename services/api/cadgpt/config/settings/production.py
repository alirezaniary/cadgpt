"""Production. Every relaxation of base has to be written down here to take effect."""

from __future__ import annotations

from cadgpt.config.settings.base import *
from cadgpt.config.settings.base import BASE_DIR, env  # noqa: F401

DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
REFRESH_COOKIE_SECURE = True

# Client drawings are unpublished work. Object storage is private with signed URLs; the
# bucket is never public-read.
if env.bool("USE_S3", default=False):
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
                "region_name": env("AWS_S3_REGION_NAME", default=""),
                "endpoint_url": env("AWS_S3_ENDPOINT_URL", default=None),
                "default_acl": None,
                "querystring_auth": True,
                "querystring_expire": 900,
                "file_overwrite": False,
                "signature_version": "s3v4",
            },
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }
