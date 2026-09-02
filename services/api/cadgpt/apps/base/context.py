"""Per-request ambient values, for the things every log line should carry.

A context variable, not thread-local storage: it survives across `await` boundaries, which
thread-locals do not, so this keeps working when a view becomes async.

Nothing load-bearing is read from here. Authorization reads the tenant off the request,
where it was resolved and checked; this exists so a log line or an audit record can be
annotated without threading four arguments through every call.
"""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
tenant_uuid_var: ContextVar[UUID | None] = ContextVar("tenant_uuid", default=None)
user_uuid_var: ContextVar[UUID | None] = ContextVar("user_uuid", default=None)


def current_request_id() -> str | None:
    return request_id_var.get()


def current_tenant_uuid() -> UUID | None:
    return tenant_uuid_var.get()


def current_user_uuid() -> UUID | None:
    return user_uuid_var.get()
