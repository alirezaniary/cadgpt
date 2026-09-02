from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from cadgpt_regulations.catalog import load_catalog, validate_catalog
from cadgpt_regulations.errors import CatalogError
from cadgpt_regulations.jsonio import JsonObject


def test_catalog_has_all_numbered_volumes_in_canonical_order() -> None:
    catalog = load_catalog()
    families = cast(list[JsonObject], catalog["families"])

    assert [family["volume"] for family in families] == list(range(1, 25))
    assert [family["catalog_order"] for family in families] == list(range(1, 25))
    assert families[6]["title_en"] == "Foundations"
    assert families[23]["title_en"] == "Urban Building Compliance"


def test_every_curated_artifact_pins_approved_source_bytes() -> None:
    artifacts = cast(list[JsonObject], load_catalog()["artifacts"])

    assert len(artifacts) == 43
    assert all(len(cast(str, artifact["expected_sha256"])) == 64 for artifact in artifacts)
    assert sum(cast(int, artifact["expected_bytes"]) for artifact in artifacts) == 479447993
    assert sum(cast(int, artifact["expected_pdf_pages"]) for artifact in artifacts) == 5892


def test_catalog_preserves_required_directed_relationships() -> None:
    artifacts = {
        artifact["catalog_key"]: artifact
        for artifact in cast(list[JsonObject], load_catalog()["artifacts"])
    }

    appendices = [
        artifact
        for artifact in artifacts.values()
        if artifact["document_kind"] == "appendix" and artifact["volume"] == 19
    ]
    appendix_orders = sorted(
        relationship["order"]
        for artifact in appendices
        for relationship in cast(list[JsonObject], artifact["relationships"])
        if relationship["type"] == "APPENDIX_OF"
    )
    assert appendix_orders == list(range(1, 10))
    assert artifacts["volume-04-protective-security-appendix-1403"]["relationships"] == [
        {
            "type": "MANDATORY_APPENDIX_OF",
            "target": "volume-04-edition-1396",
            "order": None,
        }
    ]
    assert _has_relation(
        artifacts["volume-07-borehole-amendment-1405"],
        "AMENDS",
        "volume-07-edition-1400",
    )
    assert _has_relation(
        artifacts["volume-11-amendment-1403-08-08"],
        "CLARIFIES",
        "volume-11-edition-1400",
    )
    assert _has_relation(
        artifacts["volume-12-supervisor-clarification-1404"],
        "CLARIFIES",
        "volume-12-edition-1392",
    )
    assert _has_relation(
        artifacts["volume-17-amendment-01"],
        "AMENDS",
        "volume-17-edition-1403",
    )
    assert _has_relation(
        artifacts["guide-masonry-perimeter-walls-v3-1404"],
        "SUPERSEDES",
        "guide-masonry-perimeter-walls-v2-1403",
    )


def test_volume_17_keeps_remote_identity_inert_and_local_storage_flat() -> None:
    artifact = next(
        artifact
        for artifact in cast(list[JsonObject], load_catalog()["artifacts"])
        if artifact["catalog_key"] == "volume-17-edition-1403"
    )

    assert "%2F" in cast(str, artifact["download_url"])
    assert artifact["remote_filename"] == (
        "mabahse/mabahse17/mabhas17-watermark-1403-02.pdf"
    )
    assert artifact["local_path"] == ("mabahse_mabahse17_mabhas17-watermark-1403-02.pdf")


def test_catalog_rejects_unknown_fields_recursively() -> None:
    catalog = load_catalog()
    first = cast(list[JsonObject], catalog["artifacts"])[0]
    cast(JsonObject, first["edition"])["guessed_from_filename"] = True

    with pytest.raises(CatalogError, match="guessed_from_filename"):
        validate_catalog(catalog)


def test_catalog_rejects_duplicate_and_self_referential_relationships() -> None:
    catalog = load_catalog()
    first = cast(list[JsonObject], catalog["artifacts"])[0]
    relationships = cast(list[JsonObject], first["relationships"])
    relationships.append(
        {"type": "EDITION_OF", "target": first["catalog_key"], "order": None}
    )

    with pytest.raises(CatalogError, match="target itself"):
        validate_catalog(catalog)


def test_guides_are_not_silently_classified_as_binding() -> None:
    artifacts = cast(list[JsonObject], load_catalog()["artifacts"])
    guide_statuses = {
        cast(str, artifact["legal_status"])
        for artifact in artifacts
        if artifact["document_kind"] in {"guide", "handbook"}
    }
    assert guide_statuses <= {"draft_nonbinding", "supplementary_nonbinding"}


def test_numbered_volume_must_link_to_its_own_family() -> None:
    catalog = load_catalog()
    first = cast(list[JsonObject], catalog["artifacts"])[0]
    relation = cast(list[JsonObject], first["relationships"])[0]
    relation["target"] = "volume-02"

    with pytest.raises(CatalogError, match="must be an edition of volume-01"):
        validate_catalog(catalog)


def test_malformed_numbered_volume_is_a_typed_catalog_error() -> None:
    catalog = load_catalog()
    first = cast(list[JsonObject], catalog["artifacts"])[0]
    first["volume"] = None

    with pytest.raises(CatalogError, match="schema error"):
        validate_catalog(catalog)


def test_family_and_artifact_keys_must_be_disjoint() -> None:
    catalog = load_catalog()
    family = cast(list[JsonObject], catalog["families"])[0]
    artifact = cast(list[JsonObject], catalog["artifacts"])[0]
    artifact["catalog_key"] = family["catalog_key"]

    with pytest.raises(CatalogError, match="keys overlap"):
        validate_catalog(catalog)


def test_malformed_catalog_file_is_a_typed_catalog_error(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(CatalogError, match="not valid JSON"):
        load_catalog(path)


def _has_relation(artifact: JsonObject, relation_type: str, target: str) -> bool:
    return any(
        relationship["type"] == relation_type and relationship["target"] == target
        for relationship in cast(list[JsonObject], artifact["relationships"])
    )
