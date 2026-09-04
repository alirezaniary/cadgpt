"""A project: the organizing container between a workspace and its reviews.

The product owner rejected a flat dashboard with rule sets, reviews, runs and reports all
on one page -- the requested shape mirrors Django admin, three levels deep: workspace,
projects, reviews, where a review's own detail page is where its runs and report live.
`Project` is the missing middle layer. See `docs/tasks/T-0073-a-project-to-hold-reviews.md`.

No soft delete here, unlike `RuleSet`: nothing yet references a project the way a check run
references a rule set, so there is nothing an archived project would need to keep readable.
A project with reviews under it is protected from deletion by `Review.project`'s
`on_delete=PROTECT` instead -- the same reasoning `Review.model_file` already carries.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.base.models import UuidBaseModel
from cadgpt.apps.project.repositories.custom_managers import ProjectManager
from cadgpt.apps.tenancy.models import TenantOwnedModel


class Project(TenantOwnedModel, UuidBaseModel):
    tenant_related_name = "projects"

    name = models.CharField(_("name"), max_length=255)
    created_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_projects",
        verbose_name=_("created by"),
    )

    objects: ClassVar[ProjectManager] = ProjectManager()

    class Meta:
        verbose_name = _("project")
        verbose_name_plural = _("projects")
        ordering = ("-created_at",)
        indexes = (models.Index(fields=("tenant", "-created_at")),)

    def __str__(self) -> str:
        return self.name
