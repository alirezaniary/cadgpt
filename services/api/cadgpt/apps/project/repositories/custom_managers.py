from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import Manager

from cadgpt.apps.project.repositories.querysets import ProjectQuerySet

if TYPE_CHECKING:
    from cadgpt.apps.project.models import Project

_Unfiltered = Manager.from_queryset(ProjectQuerySet)

if TYPE_CHECKING:
    _Base = _Unfiltered["Project"]
else:
    _Base = _Unfiltered


class ProjectManager(_Base):  # type: ignore[misc,valid-type]
    """A plain write wrapper. No soft-delete split: `RuleSetManager`'s three managers
    exist because a completed run's rule set must stay readable after archiving; nothing
    here yet has that reason, so there is one manager and one view of the table.
    """

    def create_project(
        self,
        *,
        tenant: Any,
        name: str,
        created_by: Any | None,
    ) -> Project:
        project = self.model(
            tenant=tenant,
            name=name.strip(),
            created_by=created_by,
        )
        project.full_clean(exclude=["tenant", "created_by"])
        project.save(using=self._db)
        return cast("Project", project)
