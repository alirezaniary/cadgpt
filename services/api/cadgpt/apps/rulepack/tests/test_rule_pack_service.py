"""A pack enters the catalogue exactly once per identity, however often it is seeded."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest
from django.core.files.storage import default_storage

from cadgpt.apps.base.exceptions import ValidationError
from cadgpt.apps.rulepack.models import RulePack
from cadgpt.apps.rulepack.repositories.querysets import RulePackQuerySet
from cadgpt.apps.rulepack.services import RulePackService

pytestmark = pytest.mark.django_db

# The same fixture RuleSetService's tests exercise, at the path services/api/conftest.py
# already computes for the whole suite.
IDS_FIXTURE = (
    Path(__file__).resolve().parents[6]
    / "packages"
    / "engine"
    / "tests"
    / "fixtures"
    / "door_width.ids"
)


def _seed(**overrides: str) -> tuple[RulePack, bool]:
    kwargs: dict[str, str] = {
        "jurisdiction": "sample",
        "region": "",
        "version": "0.1",
        "source_citation": "test fixture",
    }
    kwargs.update(overrides)
    return RulePackService().seed(ids_path=IDS_FIXTURE, **kwargs)


def test_seeding_a_pack_records_what_it_will_check() -> None:
    pack, created = _seed()
    assert created is True
    assert pack.title == "Accessible door width"
    assert pack.specification_count == 1
    assert pack.jurisdiction == "sample"
    assert pack.source_file.name


def test_seeding_the_same_identity_twice_creates_nothing_the_second_time() -> None:
    first, first_created = _seed()
    second, second_created = _seed()

    assert first_created is True
    assert second_created is False
    assert second.pk == first.pk
    assert RulePack.objects.count() == 1


def test_a_different_version_is_a_different_pack() -> None:
    _seed(version="0.1")
    _seed(version="0.2")
    assert RulePack.objects.count() == 2


def test_a_malformed_ids_is_refused() -> None:
    with tempfile.NamedTemporaryFile(suffix=".ids", delete=False) as handle:
        handle.write(b"<ids>not an ids</ids>")
        path = Path(handle.name)
    try:
        with pytest.raises(ValidationError):
            RulePackService().seed(
                ids_path=path,
                jurisdiction="sample",
                region="",
                version="0.1",
                source_citation="test fixture",
            )
    finally:
        path.unlink(missing_ok=True)
    assert RulePack.objects.count() == 0


@pytest.mark.parametrize("blank_citation", ["", "   "])
def test_a_blank_or_whitespace_only_citation_is_refused(blank_citation: str) -> None:
    """`source_citation` is required: a pack shipped under our name is an assertion, and
    an unattributed one is not publishable (`RulePack.source_citation`'s own docstring).
    Correct today, and untested until now.
    """
    with pytest.raises(ValidationError):
        _seed(source_citation=blank_citation)
    assert RulePack.objects.count() == 0


def test_a_race_that_passes_every_unlocked_read_still_creates_only_one_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T-0043: two concurrent `manage.py seed_rule_packs` runs -- two API replicas, or a
    per-container deploy hook -- can both read an empty catalogue before either has
    committed. The identity pre-check in `RulePackService.seed` and `full_clean`'s own
    `validate_unique` are both unlocked reads that a genuine second transaction could
    pass exactly as the first one did.

    Driven deterministically, not with genuine concurrency: the test suite's database is
    sqlite `:memory:` (`cadgpt.config.settings.test`), which cannot host two real
    connections against the same schema at once. So the second call is forced to see
    what a racing process would have seen -- nothing -- by making its pre-check miss
    once and its `full_clean` skip the uniqueness check it would otherwise (correctly)
    fail on. What is left to stop the duplicate is exactly what stops it in a real race:
    the database's own `unique_rule_pack_identity` constraint, nothing mocked about it.
    """
    first, first_created = _seed()
    assert first_created is True
    assert RulePack.objects.count() == 1

    _, files_before = default_storage.listdir("rule-packs/sample")

    original_matching = RulePackQuerySet.matching
    state = {"missed_once": False}

    def matching_that_misses_once(
        self: RulePackQuerySet, **kwargs: str
    ) -> RulePackQuerySet:
        if not state["missed_once"]:
            state["missed_once"] = True
            return self.none()
        return original_matching(self, **kwargs)

    monkeypatch.setattr(RulePackQuerySet, "matching", matching_that_misses_once)

    def skip_constraint_validation(self: RulePack, exclude: Any = None) -> None:
        # `full_clean` validates `Meta.constraints` (Django >= 4.1) through this method,
        # separate from `validate_unique` -- `unique_rule_pack_identity` is a
        # `UniqueConstraint`, not a field-level `unique=True`, so this is the check that
        # would otherwise also catch the collision here. It is forced to miss too,
        # exactly as a real race's second transaction would (its own
        # `validate_constraints` query runs before either side has committed).
        return None

    monkeypatch.setattr(RulePack, "validate_constraints", skip_constraint_validation)

    second, second_created = _seed()

    assert second_created is False
    assert second.pk == first.pk
    assert RulePack.objects.count() == 1

    _, files_after = default_storage.listdir("rule-packs/sample")
    assert set(files_after) == set(files_before), (
        "the losing side of the race left an orphan file in storage"
    )
