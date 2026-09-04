from __future__ import annotations

from typing import TYPE_CHECKING

from cadgpt.apps.base.querysets import TenantScopedQuerySet

if TYPE_CHECKING:
    # Imported for the quoted type parameter on the queryset below, which ruff does not
    # read as a use. Importing at runtime would be a cycle: the model module imports the
    # manager, which imports this one.
    from cadgpt.apps.project.models import Project  # noqa: F401


class ProjectQuerySet(TenantScopedQuerySet["Project"]):
    """Nothing beyond what `for_tenant` gives it.

    No `with_inputs`/`with_latest_run` equivalent is needed yet -- a project carries no
    relation a list or detail view has to prefetch. `ProjectViewSet.get_queryset`
    annotates the review count directly, since that is a single aggregate rather than a
    reusable query shape.
    """
