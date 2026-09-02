from __future__ import annotations

from typing import TYPE_CHECKING, Self

from cadgpt.apps.base.querysets import BaseQuerySet, TenantScopedQuerySet

if TYPE_CHECKING:
    # Imported for the quoted type parameters on the querysets below, which ruff
    # does not read as a use. Importing at runtime would be a cycle: the model
    # module imports the manager, which imports this one.
    from cadgpt.apps.rulepack.models import RulePack, RuleSet  # noqa: F401


class RuleSetQuerySet(TenantScopedQuerySet["RuleSet"]):
    def alive(self) -> Self:
        return self.filter(deleted_at__isnull=True)

    def dead(self) -> Self:
        return self.filter(deleted_at__isnull=False)

    def with_file(self) -> Self:
        return self.select_related("source_file", "created_by")

    def named(self, name: str) -> Self:
        return self.filter(name__iexact=name.strip())


class RulePackQuerySet(BaseQuerySet["RulePack"]):
    """No `for_tenant` here on purpose: `RulePack` is not tenant data, so there is
    nothing to scope a read by. Every tenant reads through the plain default manager.
    """

    def matching(self, *, jurisdiction: str, region: str, version: str, name: str) -> Self:
        """The pack identity a seed run checks before creating anything.

        (jurisdiction, region, version, name) is the natural key -- the same fields the
        unique constraint on `RulePack` enforces -- so a re-run finds exactly the row an
        earlier run would have created, never more and never fewer.
        """
        return self.filter(
            jurisdiction=jurisdiction, region=region, version=version, name=name
        )
