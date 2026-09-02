from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.errors import ManifestError
from cadgpt_regulations.inventory import build_inventory
from cadgpt_regulations.jsonio import JsonObject
from cadgpt_regulations.validation import check_publishable, validate_manifest


def test_schema_valid_quarantine_is_inventory_valid_but_not_publishable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    filename = "guide-masonry-perimeter-walls-v3-1404.pdf"
    payload = b"<!doctype html><html></html>"
    (source / filename).write_bytes(payload)
    catalog = load_catalog()
    artifact = next(
        artifact
        for artifact in cast(list[JsonObject], catalog["artifacts"])
        if artifact["local_path"] == filename
    )
    artifact["expected_sha256"] = hashlib.sha256(payload).hexdigest()
    artifact["expected_bytes"] = len(payload)
    manifest = build_inventory(source, catalog=catalog)

    validate_manifest(manifest, catalog=catalog)
    blockers = check_publishable(manifest, catalog=catalog)

    assert any(
        blocker.local_path == filename and blocker.code == "MEDIA_TYPE_MISMATCH"
        for blocker in blockers
    )
    assert any(blocker.code == "EXPECTED_ARTIFACT_MISSING" for blocker in blockers)


def test_manifest_schema_rejects_unknown_fields(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    write_pdf(source / "mabhas-1.pdf")
    manifest = build_inventory(source)
    first = cast(list[JsonObject], manifest["artifacts"])[0]
    first["silently_approved"] = True

    with pytest.raises(ManifestError, match="silently_approved"):
        validate_manifest(manifest)


def test_manifest_cannot_hide_a_deleted_catalog_record(tmp_path: Path) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    manifest = build_inventory(source)
    cast(list[JsonObject], manifest["artifacts"]).pop()

    with pytest.raises(ManifestError, match="catalog coverage differs"):
        validate_manifest(manifest)


def test_manifest_cannot_relabel_curated_metadata(tmp_path: Path) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    manifest = build_inventory(source)
    first = cast(list[JsonObject], manifest["artifacts"])[0]
    first["legal_status"] = "supplementary_nonbinding"

    with pytest.raises(ManifestError, match="differs at legal_status"):
        validate_manifest(manifest)


def test_unaccounted_artifact_cannot_be_marked_ready(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    write_pdf(source / "surprise.pdf")
    manifest = build_inventory(source)
    surprise = next(
        artifact
        for artifact in cast(list[JsonObject], manifest["artifacts"])
        if artifact["catalog_key"] is None
    )
    surprise["artifact_state"] = "ready"
    surprise["error"] = None

    with pytest.raises(ManifestError, match="unaccounted artifact"):
        validate_manifest(manifest)


def test_manifest_is_bound_to_the_exact_catalog_digest(tmp_path: Path) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    manifest = build_inventory(source)
    cast(JsonObject, manifest["catalog"])["sha256"] = "0" * 64

    with pytest.raises(ManifestError, match="digest does not match"):
        validate_manifest(manifest)


def test_ready_state_requires_real_pdf_metadata(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    path = source / "mabhas-1.pdf"
    write_pdf(path)
    catalog = load_catalog()
    first_catalog = cast(list[JsonObject], catalog["artifacts"])[0]
    first_catalog["expected_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    first_catalog["expected_bytes"] = path.stat().st_size
    first_catalog["expected_pdf_pages"] = 1
    manifest = build_inventory(source, catalog=catalog)
    first = cast(list[JsonObject], manifest["artifacts"])[0]
    first["pdf_page_count"] = None

    with pytest.raises(ManifestError, match="schema error"):
        validate_manifest(manifest)


def test_wrong_source_hash_cannot_be_relabelled_ready(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    write_pdf(source / "mabhas-1.pdf")
    manifest = build_inventory(source)
    first = cast(list[JsonObject], manifest["artifacts"])[0]
    assert cast(JsonObject, first["error"])["code"] == "SOURCE_HASH_MISMATCH"
    first["artifact_state"] = "ready"
    first["error"] = None
    first["pdf_page_count"] = 1

    with pytest.raises(ManifestError, match="approved source bytes"):
        validate_manifest(manifest)


def test_complete_arbitrary_inventory_cannot_pass_publication(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    catalog = load_catalog()
    artifacts = cast(list[JsonObject], catalog["artifacts"])
    for artifact in artifacts:
        write_pdf(source / cast(str, artifact["local_path"]))
        artifact["review_status"] = "accepted"
        artifact["review_flags"] = []

    manifest = build_inventory(source, catalog=catalog)

    validate_manifest(manifest, catalog=catalog)
    blockers = check_publishable(manifest, catalog=catalog)
    assert len(blockers) == 43
    assert {blocker.code for blocker in blockers} == {"SOURCE_HASH_MISMATCH"}
