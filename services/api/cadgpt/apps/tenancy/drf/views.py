"""The tenant-scoped viewset. Every route touching tenant data inherits it.

It lives in the tenancy app rather than in `base` because it needs tenant resolution, and
`base` is the lowest layer of the import contract -- it may not know that tenants exist.
Discovering that is what the contract is for: the dependency wanted to point the wrong
way, and moving the class is the fix rather than exempting the import.
"""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Model, QuerySet

from cadgpt.apps.base.drf.views import BaseViewSet
from cadgpt.apps.tenancy.resolution import current_tenant


class TenantScopedViewSet(BaseViewSet):
    """Every read and write is confined to the tenant resolved for this request.

    This is the isolation boundary. There is no database row-level security behind it, so
    narrowing `get_queryset` to the request's tenant is the only thing standing between
    two firms' unpublished models -- which is why it lives in a base class no subclass may
    bypass, and why `tests/test_tenant_isolation.py` walks every registered route and
    fails the build if one over a tenant-owned model does not inherit from here.

    `for_tenant(None)` yields nothing, so a request that somehow lost its tenant returns
    an empty list rather than everything.
    """

    def get_queryset(self) -> QuerySet[Model]:
        queryset = self.tenant_queryset()
        if (selectors := self.queryset_selectors.get(self.action)) is not None:
            queryset = queryset.select_related(*selectors)
        return cast("QuerySet[Model]", queryset)

    def tenant_queryset(self) -> Any:
        """The base queryset for this viewset, already narrowed to the tenant."""
        assert self.queryset is not None, f"{type(self).__name__} must declare `queryset`."
        return cast(Any, self.queryset).for_tenant(self.tenant)

    @property
    def tenant(self) -> Any:
        """Resolved on demand, after authentication. See `tenancy.resolution`."""
        return current_tenant(self.request)
