from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.errors import InventoryError
from cadgpt_regulations.inventory import (
    build_inventory,
    ensure_output_outside_source,
    write_inventory,
)
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes


def test_inventory_is_byte_deterministic_and_hashes_source_bytes(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    artifact = source / "deterministic.pdf"
    write_pdf(artifact, 2)

    first = build_inventory(source)
    second = build_inventory(source)
    record = _record(first, "deterministic.pdf")

    assert canonical_bytes(first) == canonical_bytes(second)
    assert record["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert record["bytes"] == artifact.stat().st_size
    assert record["pdf_page_count"] == 2
    assert "generated_at" not in first


def test_known_persian_filename_with_wrong_valid_pdf_is_quarantined(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    filename = "اصلاحیه-1-مبحث-17.pdf"
    write_pdf(source / filename)

    record = _record(build_inventory(source), filename)

    assert record["catalog_key"] == "volume-17-amendment-01"
    assert record["original_filename"] == filename
    assert record["artifact_state"] == "quarantined"
    assert cast(JsonObject, record["error"])["code"] == "SOURCE_HASH_MISMATCH"
    assert record["pdf_page_count"] is None


def test_html_with_pdf_suffix_is_quarantined_by_content(tmp_path: Path) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    filename = "راهنمای-طراحی-دیوارهای-بنایی-محوطه.pdf"
    payload = b"<!doctype html><html><title>official landing page</title></html>"
    (source / filename).write_bytes(payload)
    catalog = load_catalog()
    _catalog_artifact(catalog, filename)["expected_sha256"] = hashlib.sha256(
        payload
    ).hexdigest()

    record = _record(build_inventory(source, catalog=catalog), filename)

    assert record["detected_media_type"] == "text/html"
    assert record["artifact_state"] == "quarantined"
    assert cast(JsonObject, record["error"])["code"] == "MEDIA_TYPE_MISMATCH"
    assert record["pdf_page_count"] is None


def test_pdfinfo_failure_is_terminal_and_does_not_abort_inventory(tmp_path: Path) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    payload = b"%PDF-1.4\nnot actually a PDF"
    (source / "mabhas-1.pdf").write_bytes(payload)
    catalog = load_catalog()
    _catalog_artifact(catalog, "mabhas-1.pdf")["expected_sha256"] = hashlib.sha256(
        payload
    ).hexdigest()

    manifest = build_inventory(source, catalog=catalog)
    record = _record(manifest, "mabhas-1.pdf")

    assert record["detected_media_type"] == "application/pdf"
    assert record["artifact_state"] == "quarantined"
    assert cast(JsonObject, record["error"])["code"] == "PDFINFO_FAILED"
    assert manifest["summary"]["files_discovered"] == 1


def test_nested_duplicate_basename_is_not_mistaken_for_expected_artifact(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    write_pdf(source / "mabhas-1.pdf")
    write_pdf(source / "nested" / "mabhas-1.pdf")

    manifest = build_inventory(source)

    assert _record(manifest, "mabhas-1.pdf")["catalog_key"] == "volume-01-edition-1392"
    nested = _record(manifest, "nested/mabhas-1.pdf")
    assert nested["catalog_key"] is None
    assert cast(JsonObject, nested["error"])["code"] == "UNACCOUNTED_ARTIFACT"
    assert manifest["summary"]["files_discovered"] == 2


def test_encoded_url_separator_never_becomes_a_local_path(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    safe_name = "mabahse_mabahse17_mabhas17-watermark-1403-02.pdf"
    write_pdf(source / safe_name)

    record = _record(build_inventory(source), safe_name)

    assert record["catalog_key"] == "volume-17-edition-1403"
    assert not (source / "mabahse" / "mabahse17").exists()


def test_output_inside_source_is_rejected_before_any_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    existing = source / "mabhas-1.pdf"
    existing.write_bytes(b"source bytes")

    with pytest.raises(InventoryError, match="outside the source"):
        ensure_output_outside_source(source, existing)
    assert existing.read_bytes() == b"source bytes"


def test_secure_temp_write_does_not_follow_predictable_symlink(tmp_path: Path) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    manifest = build_inventory(source)
    output = tmp_path / "manifest.json"
    victim = tmp_path / "victim.txt"
    victim.write_text("do not overwrite", encoding="utf-8")
    old_predictable_temp = tmp_path / ".manifest.json.tmp"
    old_predictable_temp.symlink_to(victim)

    write_inventory(manifest, output)

    assert victim.read_text(encoding="utf-8") == "do not overwrite"
    assert output.read_bytes() == canonical_bytes(manifest)
    assert old_predictable_temp.is_symlink()


def test_output_symlink_and_non_regular_targets_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    manifest = build_inventory(source)
    victim = tmp_path / "victim.txt"
    victim.write_text("do not overwrite", encoding="utf-8")
    symlink_output = tmp_path / "manifest-link.json"
    symlink_output.symlink_to(victim)

    with pytest.raises(InventoryError, match="not a regular file"):
        write_inventory(manifest, symlink_output)
    assert victim.read_text(encoding="utf-8") == "do not overwrite"

    directory_output = tmp_path / "manifest-directory"
    directory_output.mkdir()
    with pytest.raises(InventoryError, match="not a regular file"):
        write_inventory(manifest, directory_output)


def test_leading_dash_filename_is_passed_safely_to_pdfinfo(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    write_pdf(source / "-unaccounted.pdf")

    record = _record(build_inventory(source), "-unaccounted.pdf")

    assert record["pdf_page_count"] == 1
    assert cast(JsonObject, record["error"])["code"] == "UNACCOUNTED_ARTIFACT"


def test_arbitrary_pdfs_with_expected_names_fail_closed_across_complete_coverage(
    tmp_path: Path, write_pdf: Callable[[Path, int], None]
) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    catalog = load_catalog()
    expected = cast(list[JsonObject], catalog["artifacts"])
    for artifact in expected:
        filename = cast(str, artifact["original_filename"])
        write_pdf(source / filename)

    manifest = build_inventory(source, catalog=catalog)
    summary = cast(JsonObject, manifest["summary"])

    assert summary == {
        "expected_artifacts": 42,
        "files_discovered": 42,
        "artifacts_accounted": 42,
        "valid_pdfs": 0,
        "quarantined": 42,
        "missing": 0,
        "unaccounted": 0,
        "needs_review": 1,
        "pdf_pages": 0,
    }
    errors = {
        cast(JsonObject, artifact["error"])["code"]
        for artifact in cast(list[JsonObject], manifest["artifacts"])
    }
    assert errors == {"SOURCE_HASH_MISMATCH"}


def _record(manifest: JsonObject, filename: str) -> JsonObject:
    records = cast(list[JsonObject], manifest["artifacts"])
    return next(record for record in records if record["original_filename"] == filename)


def _catalog_artifact(catalog: JsonObject, filename: str) -> JsonObject:
    artifacts = cast(list[JsonObject], catalog["artifacts"])
    return next(
        artifact for artifact in artifacts if artifact["original_filename"] == filename
    )
