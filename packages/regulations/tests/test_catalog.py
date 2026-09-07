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
    assert sum(cast(int, artifact["expected_bytes"]) for artifact in artifacts) == 470674872
    assert sum(cast(int, artifact["expected_pdf_pages"]) for artifact in artifacts) == 5892


def test_catalog_pins_explicit_volume_11_and_24_replacements() -> None:
    catalog = load_catalog()
    artifacts = {
        cast(str, artifact["catalog_key"]): artifact
        for artifact in cast(list[JsonObject], catalog["artifacts"])
    }

    volume_11 = artifacts["volume-11-edition-1400"]
    assert volume_11["download_url"] == (
        "https://inbr.ir/wp-content/uploads/2026/08/mabhas11-2.pdf"
    )
    assert volume_11["remote_filename"] == "m11-2.pdf"
    assert volume_11["local_path"] == "m11-2.pdf"
    assert volume_11["expected_sha256"] == (
        "07283f909f9e7c3f9189f6518a1ec9f3215025c78d72727e19528282794ad477"
    )
    assert volume_11["expected_bytes"] == 13622631
    assert volume_11["expected_pdf_pages"] == 144
    assert volume_11["edition"] == {
        "edition_number": 3,
        "label_en": "Third edition",
        "label_fa": "ویرایش سوم",
        "publication_date_shamsi": None,
        "publication_year_shamsi": "1400",
    }
    assert _has_relation(
        artifacts["volume-11-amendment-1403-08-08"],
        "AMENDS",
        "volume-11-edition-1400",
    )

    volume_24 = artifacts["volume-24-current-1404"]
    assert volume_24["download_url"] == (
        "https://inbr.ir/wp-content/uploads/2026/08/mabhas24-4.pdf"
    )
    assert volume_24["remote_filename"] == "mabhas24-4.pdf"
    assert volume_24["local_path"] == "mabhas24-4.pdf"
    assert volume_24["expected_sha256"] == (
        "3a5bfd8efb03b8dc53c8bcd00c3e432c71f6b99f729344ff015570a679076623"
    )
    assert volume_24["expected_bytes"] == 2975003
    assert volume_24["expected_pdf_pages"] == 53
    assert volume_24["edition"] == {
        "edition_number": 1,
        "label_en": "First edition",
        "label_fa": "ویرایش اول",
        "publication_date_shamsi": None,
        "publication_year_shamsi": "1404",
    }

    sources = cast(list[JsonObject], catalog["metadata_sources"])
    assert [(source["catalog_order"], source["source_key"]) for source in sources] == [
        (1, "page-104"),
        (2, "page-1160"),
        (3, "page-5825"),
        (4, "post-5713"),
        (5, "post-6022"),
        (6, "post-6691"),
        (7, "post-6735"),
        (8, "post-7042"),
        (9, "post-7061"),
        (10, "post-7064"),
    ]
    source_by_key = {cast(str, source["source_key"]): source for source in sources}
    assert source_by_key["post-7042"]["expected_semantic_sha256"] == (
        "4ae2698e1dfb3af71fd35a2232619fc629f3c1e6ef098b941da7a5db19a8b278"
    )
    assert source_by_key["post-7061"]["expected_semantic_sha256"] == (
        "7617d3c325fed255b5d9715adfd1359cd37fd2b553a44aeee4f07339f0e0425d"
    )


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
