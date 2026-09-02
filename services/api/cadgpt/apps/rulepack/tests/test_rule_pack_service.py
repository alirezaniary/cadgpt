"""A pack enters the catalogue exactly once per identity, however often it is seeded."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cadgpt.apps.base.exceptions import ValidationError
from cadgpt.apps.rulepack.models import RulePack
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
