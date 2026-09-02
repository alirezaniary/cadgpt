"""Service base classes. All business logic lives in a service.

Not in a serializer, which exists only in an HTTP request; not in a model, which has to
stay callable during a migration; not in a view, which cannot be reached from a worker.
A service is a plain object with a tenant, so the same call works from a request, a Celery
task, a management command, and -- later -- an MCP tool the connector drives.
"""

from __future__ import annotations

from typing import Any

import structlog


class BaseService:
    """A service with no tenant: registration, and the tenant lifecycle itself."""

    def __init__(self) -> None:
        self.log: Any = structlog.get_logger(type(self).__module__).bind(
            service=type(self).__name__
        )


class BaseTenantAwareService(BaseService):
    """A service bound to exactly one tenant for its whole lifetime.

    The tenant is a constructor argument rather than an argument to each method, so there
    is no call site where it can be omitted, and no method that can be handed a different
    tenant than the one the caller was authorized for.
    """

    def __init__(self, tenant: Any) -> None:
        if tenant is None:
            raise ValueError(
                "A tenant-aware service cannot be constructed without a tenant."
            )
        super().__init__()
        self.tenant = tenant
        self.log = self.log.bind(tenant_id=str(tenant.uuid))
