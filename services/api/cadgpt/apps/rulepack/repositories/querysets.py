from __future__ import annotations

from typing import TYPE_CHECKING, Self

from cadgpt.apps.base.querysets import TenantScopedQuerySet

if TYPE_CHECKING:
    # Imported for the quoted type parameter on the queryset below, which ruff
    # does not read as a use. Importing at runtime would be a cycle: the model
    # module imports the manager, which imports this one.
    from cadgpt.apps.rulepack.models import RuleSet  # noqa: F401


class RuleSetQuerySet(TenantScopedQuerySet["RuleSet"]):
    def alive(self) -> Self:
        return self.filter(deleted_at__isnull=True)

    def dead(self) -> Self:
        return self.filter(deleted_at__isnull=False)

    def with_file(self) -> Self:
        return self.select_related("source_file", "created_by")

    def named(self, name: str) -> Self:
        return self.filter(name__iexact=name.strip())
