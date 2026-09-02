# The API and the Celery worker are the same image with different commands: they run the
# same code over the same models, and a worker built separately is a worker that drifts.

FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# ifcopenshell carries its own native libraries but still links against the system C++
# runtime and zlib.
# gettext is needed to compile the message catalogues: the product's tenants are
# multinational and an English-only error is unusable to half of them.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libstdc++6 zlib1g curl gettext \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app

# ---------------------------------------------------------------------------- deps
# Dependency resolution is cached on the lockfile alone, so editing source does not
# reinstall ifcopenshell.
FROM base AS deps

COPY pyproject.toml uv.lock ./
COPY packages/engine/pyproject.toml packages/engine/
COPY services/api/pyproject.toml services/api/
RUN uv sync --frozen --no-dev --no-install-workspace

# ---------------------------------------------------------------------------- runtime
FROM deps AS runtime

COPY packages/engine packages/engine
COPY services/api services/api
RUN uv sync --frozen --no-dev

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/services/api \
    DJANGO_SETTINGS_MODULE=cadgpt.config.settings.production

# Compiled at build time so a running container never depends on gettext being present,
# and so a broken catalogue fails the build rather than a user's request.
RUN cd /app/services/api \
    && DJANGO_SETTINGS_MODULE=cadgpt.config.settings.test \
       python manage.py compilemessages --ignore=node_modules

# Never root: a checker that parses arbitrary uploaded files is exactly the process you
# do not want owning the filesystem.
RUN useradd --system --create-home --uid 10001 cadgpt \
    && mkdir -p /app/services/api/mediafiles /app/services/api/staticfiles \
    && chown -R cadgpt:cadgpt /app
USER cadgpt

WORKDIR /app/services/api
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["gunicorn", "cadgpt.config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "120", \
     "--access-logfile", "-"]
