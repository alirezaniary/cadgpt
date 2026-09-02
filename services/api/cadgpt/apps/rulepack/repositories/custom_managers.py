from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import Manager

from cadgpt.apps.rulepack.repositories.querysets import RulePackQuerySet, RuleSetQuerySet

if TYPE_CHECKING:
    from cadgpt.apps.rulepack.models import RulePack, RuleSet

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


_UnfilteredRulePack = Manager.from_queryset(RulePackQuerySet)

if TYPE_CHECKING:
    _RulePackBase = _UnfilteredRulePack["RulePack"]
else:
    _RulePackBase = _UnfilteredRulePack


class RulePackManager(_RulePackBase):  # type: ignore[misc,valid-type]
    """Thin write wrapper. Whether a pack belongs in the catalogue was decided by the
    seeding service, never here -- this only persists what it is given.
    """

    def create_rule_pack(
        self,
        *,
        name: str,
        description: str,
        jurisdiction: str,
        region: str,
        version: str,
        source_file: Any,
        source_citation: str,
        title: str,
        author: str,
        specification_count: int,
    ) -> RulePack:
        rule_pack = self.model(
            name=name.strip(),
            description=description.strip(),
            jurisdiction=jurisdiction.strip(),
            region=region.strip(),
            version=version.strip(),
            source_citation=source_citation.strip(),
            title=title[:255],
            author=author[:255],
            specification_count=specification_count,
        )
        rule_pack.source_file = source_file
        rule_pack.full_clean(exclude=["source_file"])
        rule_pack.save(using=self._db)
        return cast("RulePack", rule_pack)
