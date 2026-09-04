"""Backfill for T-0073: every tenant with at least one existing review gets one project
named "عمومی" ("General"), and every one of that tenant's reviews is pointed at it.

Persian, hardcoded rather than run through `gettext`: this is scaffolding for rows that
predate `Project` existing at all, not a designer-facing string, and it takes the app's
one hardcoded language like everything else per T-0072.

Not reversible: reversing would have to guess which of a tenant's projects this migration
created versus one created since by a real request, and delete accordingly. `0006` keeps
`project` nullable specifically so this state -- the schema before this data migration
ran -- is always reachable without deleting anything; going back further than that is not
a supported direction.
"""

from __future__ import annotations

from typing import Any

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def backfill_general_projects(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    project_model: Any = apps.get_model("project", "Project")
    review_model: Any = apps.get_model("review", "Review")

    tenant_ids = (
        review_model.objects.filter(project__isnull=True)
        .order_by("tenant_id")
        .values_list("tenant_id", flat=True)
        .distinct()
    )
    for tenant_id in tenant_ids:
        project = project_model.objects.create(tenant_id=tenant_id, name="عمومی")
        review_model.objects.filter(tenant_id=tenant_id, project__isnull=True).update(
            project=project
        )


class Migration(migrations.Migration):

    dependencies = [
        ("review", "0006_review_project"),
    ]

    operations = [
        migrations.RunPython(backfill_general_projects, migrations.RunPython.noop),
    ]
