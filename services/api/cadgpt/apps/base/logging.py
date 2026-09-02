"""Structured logging.

JSON in production so a log aggregator can index it; a readable console renderer in
development. Every event carries the request id, the tenant and the user, pulled from the
ambient context rather than passed in, so no call site can forget them.

Sensitive fields are dropped centrally rather than avoided by discipline: a password,
token or secret that reaches a log line is redacted by the processor chain, wherever it
came from.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, cast

import structlog

from cadgpt.apps.base.context import (
    current_request_id,
    current_tenant_uuid,
    current_user_uuid,
)

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "new_password",
        "old_password",
        "token",
        "access",
        "refresh",
        "secret",
        "authorization",
        "api_key",
        "national_code",
        "phone",
        "phone_number",
    }
)


def add_request_context(
    _logger: Any, _method: str, event: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Attach the ambient request, tenant and user identifiers to every event."""
    if (request_id := current_request_id()) is not None:
        event.setdefault("request_id", request_id)
    if (tenant_uuid := current_tenant_uuid()) is not None:
        event.setdefault("tenant_id", str(tenant_uuid))
    if (user_uuid := current_user_uuid()) is not None:
        event.setdefault("user_id", str(user_uuid))
    return event


def redact_sensitive(_logger: Any, _method: str, event: dict[str, Any]) -> dict[str, Any]:
    """Replace the value of any key that names a credential.

    Central redaction, because "never log a password" as a rule survives exactly as long
    as the person who remembers it.
    """
    for key in list(event):
        if key.lower() in SENSITIVE_KEYS:
            event[key] = "[redacted]"
    return event


def configure(*, json_output: bool) -> None:
    """Install the processor chain. Called once from the base app's `ready()`."""
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            cast(Any, add_request_context),
            cast(Any, redact_sensitive),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        cache_logger_on_first_use=True,
    )
