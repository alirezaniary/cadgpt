"""Liveness and readiness, which are different questions and must not share an answer.

`healthz` says the process is up. If it checked the database, a database blip would make
the orchestrator kill healthy web processes and turn an outage into a longer outage.

`readyz` says this process can serve traffic right now -- database reachable, broker
reachable -- and a failure takes it out of the load balancer without restarting it.
"""

from __future__ import annotations

from typing import Any

from django.db import connections
from django.http import HttpRequest, JsonResponse

from cadgpt.config.celery import app as celery_app


def healthz(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def readyz(_request: HttpRequest) -> JsonResponse:
    checks: dict[str, Any] = {}

    try:
        connections["default"].cursor().execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        checks["database"] = f"error: {exc}"
    else:
        checks["database"] = "ok"

    try:
        celery_app.connection().ensure_connection(max_retries=0, timeout=2)
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        checks["broker"] = f"error: {exc}"
    else:
        checks["broker"] = "ok"

    ready = all(value == "ok" for value in checks.values())
    return JsonResponse(
        {"status": "ready" if ready else "not ready", "checks": checks},
        status=200 if ready else 503,
    )
