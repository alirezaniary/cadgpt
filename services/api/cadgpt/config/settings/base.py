"""Settings shared by every environment.

Nothing here reads a secret with a usable default. A deployment that forgets to set one
fails at startup rather than running on a value an attacker can read in this file.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import environ
from django.utils.translation import gettext_lazy as _

# cadgpt/config/settings/base.py -> services/api
BASE_DIR = Path(__file__).resolve().parents[3]

env = environ.Env()
env.read_env(str(BASE_DIR / ".env"), overwrite=False)

SECRET_KEY: str = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])

# --------------------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
]

# Order matches the import-contract layering in the root pyproject.toml: a lower app never
# depends on a higher one.
LOCAL_APPS = [
    "cadgpt.apps.base",
    "cadgpt.apps.account",
    "cadgpt.apps.tenancy",
    "cadgpt.apps.media",
    "cadgpt.apps.rulepack",
    "cadgpt.apps.review",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # The tenant is deliberately not resolved here: authentication is a bearer token
    # checked by DRF inside the view, so no middleware can know who is calling.
    # See cadgpt.apps.tenancy.resolution.
    "cadgpt.apps.base.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "cadgpt.config.urls"
WSGI_APPLICATION = "cadgpt.config.wsgi.application"
ASGI_APPLICATION = "cadgpt.config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "cadgpt" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------------------

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=60)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "account.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------------------
# Internationalization
#
# The product is jurisdiction-agnostic and its tenants are not (PRD I4). Every
# user-facing string goes through gettext; none is written in English at the call site.
# --------------------------------------------------------------------------------------

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", _("English")),
    ("fa", _("Persian")),
]
LOCALE_PATHS = [BASE_DIR / "cadgpt" / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

STORAGES: dict[str, dict[str, Any]] = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Uploads are building models: tens of megabytes is ordinary, and streaming them to a
# temporary file rather than into memory is what keeps a worker's footprint bounded.
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024

# Derived, not guessed -- T-0033 (docs/tasks/T-0033-measured-upload-ceiling.md),
# reasoning in docs/decisions.md. `scripts/measure_check_memory.py` measured peak RSS of
# a real `run_check` over three model sizes in the `cadgpt-api:latest` image:
#
#   Duplex 2.3MB -> 173MB peak RSS | Schependomlaan 47MB -> 642MB | large 94.4MB -> 1202MB
#
# which fits peak_RSS_MB ~= 87 + 11.8 * size_MB for models at this scale. The worker
# (`deploy/compose.yaml`) runs `--concurrency 2` inside one container now declared with a
# 4 GiB `mem_limit`: two checks can run at once, sharing that one budget, so the number
# below is a *per-check* ceiling, not the container's. Reserving ~150MB for the Celery
# parent process leaves ~1973MB per concurrent check; keeping to 80% of that for
# allocator/GC slack and rule sets that walk more of the model than door_width.ids did
# gives a ~1578MB usable budget. Solving the fit for that budget gives ~126.3MB -- taken
# as-is, rounded only to a whole megabyte (the input measurements carry no more precision
# than that), not reduced further for a rounder or more memorable number. The prior
# version of this constant did exactly that (100MB, discarding ~26MB the measurement
# actually supports) and a T-0033 review caught it: docs/decisions.md documents the
# correction. This number moves if `--concurrency`, the container's `mem_limit`, or the
# 80% safety factor changes -- it is not independent of them.
#
# What this does NOT establish: the plan's other clause -- "high enough to serve 95% of
# users" -- is a demand-side claim this repository has no upload-size corpus to check
# against. One 47MB real sample is not a distribution. See docs/decisions.md and this
# task's Evidence, NOT DONE.
MAX_UPLOAD_BYTES = env.int("MAX_UPLOAD_BYTES", default=126 * 1024 * 1024)

# --------------------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "cadgpt.apps.base.drf.pagination.SimplePagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "cadgpt.apps.base.drf.exception_handler.problem_detail_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth": "10/min",
        "upload": "60/hour",
        "check": "120/hour",
    },
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "CADGPT API",
    "DESCRIPTION": (
        "Check IFC models against IDS rule sets and report what passes, what fails, and "
        "what could not be determined."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v[0-9]",
    "ENUM_NAME_OVERRIDES": {
        "OutcomeStatus": "cadgpt.apps.review.choices.OUTCOME_STATUS_CHOICES",
    },
}

ACCESS_TOKEN_MINUTES = env.int("JWT_ACCESS_MINUTES", default=15)
REFRESH_TOKEN_DAYS = env.int("JWT_REFRESH_DAYS", default=14)

SIMPLE_JWT = {
    # simplejwt requires timedeltas here, not numbers. Passing an int type-checks, starts
    # cleanly, and fails only when the first token is issued.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=ACCESS_TOKEN_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=REFRESH_TOKEN_DAYS),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "uuid",
    "USER_ID_CLAIM": "sub",
}

# The refresh token is delivered as an httpOnly cookie and never reaches JavaScript; the
# access token lives in the SPA's memory only. An XSS in the frontend then cannot lift a
# credential that outlives the page.
REFRESH_COOKIE_NAME = "cadgpt_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth/"
REFRESH_COOKIE_SECURE = True
REFRESH_COOKIE_SAMESITE = "Lax"

CORS_ALLOWED_ORIGINS: list[str] = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS: list[str] = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --------------------------------------------------------------------------------------
# Background work
# --------------------------------------------------------------------------------------

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=1800)
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=1500)
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": CELERY_TASK_TIME_LIMIT + 60}
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {"review.tasks.*": {"queue": "checks"}}

# A run left RUNNING for longer than this had its worker die. It is failed explicitly
# rather than left to look like work still in progress.
CHECK_RUN_STALL_SECONDS = env.int("CHECK_RUN_STALL_SECONDS", default=CELERY_TASK_TIME_LIMIT)

# How many times `CheckRunExecutor._claim` will re-claim the same run after a worker died
# holding it, before ending it as `CheckRunFailure.RESOURCE_EXHAUSTED` instead of trying
# again. T-0033: `acks_late` + a re-claimable `RUNNING` run is correct for a worker killed
# by a deploy, and a poison message for one killed by the OOM killer -- without a bound, a
# model that exhausts memory is redelivered, claimed and killed again forever, starving
# every other tenant on the shared `checks` queue. `claim_count` is incremented in the
# same row-locked transaction that flips the run to `RUNNING`, not after the expensive
# work starts, so the count survives a kill at any point after the claim is recorded and
# never undercounts an attempt that got that far.
CHECK_RUN_MAX_CLAIMS = env.int("CHECK_RUN_MAX_CLAIMS", default=3)

# How many non-passing elements one requirement itemises in a stored report. Counts stay
# exact regardless; see cadgpt_engine.report.
CHECK_ENTITY_LIMIT = env.int("CHECK_ENTITY_LIMIT", default=500)

# --------------------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------------------

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False

TENANT_HEADER = "HTTP_X_TENANT"
