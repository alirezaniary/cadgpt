from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import Manager

from cadgpt.apps.rulepack.repositories.querysets import RuleSetQuerySet

if TYPE_CHECKING:
    from cadgpt.apps.rulepack.models import RuleSet

_Unfiltered = Manager.from_queryset(RuleSetQuerySet)

if TYPE_CHECKING:
    _Base = _Unfiltered["RuleSet"]
else:
    _Base = _Unfiltered


class RuleSetManager(_Base):  # type: ignore[misc,valid-type]
    """Hides soft-deleted rows by default; the other two views are named explicitly."""

    def get_queryset(self) -> RuleSetQuerySet:
        return cast(RuleSetQuerySet, super().get_queryset()).alive()

    def create_rule_set(
        self,
        *,
        tenant: Any,
        name: str,
        description: str,
        source_file: Any,
        title: str,
        author: str,
        version: str,
        specification_count: int,
        created_by: Any | None,
    ) -> RuleSet:
        rule_set = self.model(
            tenant=tenant,
            name=name.strip(),
            description=description.strip(),
            source_file=source_file,
            title=title[:255],
            author=author[:255],
            version=version[:64],
            specification_count=specification_count,
            created_by=created_by,
        )
        rule_set.full_clean(exclude=["tenant", "source_file", "created_by"])
        rule_set.save(using=self._db)
        return cast("RuleSet", rule_set)


class DeletedRuleSetManager(_Base):  # type: ignore[misc,valid-type]
    """Only the archived rows, for restoring one or auditing what was removed."""

    def get_queryset(self) -> RuleSetQuerySet:
        return cast(RuleSetQuerySet, super().get_queryset()).dead()


class AllRuleSetManager(_Base):  # type: ignore[misc,valid-type]
    """Every row, archived or not. What a completed run's report reads through."""
