from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from cadgpt_regulations.errors import TranscriptionError
from cadgpt_regulations.page_tools import run_probe_worker
from cadgpt_regulations.store_index import validate_output_inventory
from cadgpt_regulations.transcription import (
    _build_bundles,
    _validate_document_bundles,
    ascii_digit_view,
    normalize_search_text,
)


def test_normalization_preserves_mathematics_identifiers_and_source_digits() -> None:
    raw = "ﻻ ي ك ۱۲\u066b۳ ≤ x² LRFD ASD\nA\t  B"

    normalized, transform_log = normalize_search_text(raw)

    assert normalized == "لا ی ک ۱۲\u066b۳ ≤ x² LRFD ASD\nA B"
    assert raw == "ﻻ ي ك ۱۲\u066b۳ ≤ x² LRFD ASD\nA\t  B"
    assert ascii_digit_view(normalized) == "لا ی ک 12\u066b3 ≤ x² LRFD ASD\nA B"
    assert transform_log["protected_views"] == [
        "source_digits",
        "operators",
        "signs",
        "decimal_separators",
        "superscripts",
        "clause_identifiers",
    ]


@pytest.mark.integration
def test_page_worker_runs_real_parser_and_renderer_in_a_subprocess(
    tmp_path: Path,
) -> None:
    source = tmp_path / "native.pdf"
    source.write_bytes(_native_pdf(b"Hello LRFD 2+2=4"))
    source.chmod(0o600)
    output = tmp_path / "output"
    output.mkdir(mode=0o700)

    result = run_probe_worker(
        source,
        page_number=1,
        page_id=f"sha256:{'a' * 64}:page:000001",
        dpi=144,
        output_directory=output,
        timeout_seconds=30,
    )

    assert result.render.startswith(b"\x89PNG\r\n\x1a\n")
    assert result.render_metrics["width_pixels"] == 1224
    assert "LRFD" in str(result.native["raw_glyph_text"])
    assert stat.S_IMODE((output / "native.json").stat().st_mode) == 0o600


@pytest.mark.integration
def test_page_worker_turns_a_corrupt_pdf_into_a_terminal_error(tmp_path: Path) -> None:
    source = tmp_path / "corrupt.pdf"
    source.write_bytes(b"not a PDF")
    source.chmod(0o600)
    output = tmp_path / "output"
    output.mkdir(mode=0o700)

    with pytest.raises(TranscriptionError, match="page worker exited"):
        run_probe_worker(
            source,
            page_number=1,
            page_id=f"sha256:{'a' * 64}:page:000001",
            dpi=144,
            output_directory=output,
            timeout_seconds=30,
        )


def test_generated_store_inventory_rejects_unindexed_empty_directories(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    (root / "unexpected").mkdir(mode=0o700)

    with pytest.raises(TranscriptionError, match="unindexed_directories"):
        validate_output_inventory(root)


def _write_bytes(path: Path, payload: bytes) -> None:
    missing: list[Path] = []
    current = path.parent
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    path.write_bytes(payload)
    path.chmod(0o600)


def _ready_page(root: Path, page_number: int) -> dict[str, object]:
    """Write the on-disk files `_bundle_page_ref` re-attests for a real, ready page."""
    source_sha256 = "a" * 64
    page_id = f"sha256:{source_sha256}:page:{page_number:06d}"
    span_id = f"{page_id}:native:line:000000"
    probe_relative = Path("probe") / f"{page_number:06d}"
    _write_bytes(
        root / probe_relative / "native.json",
        json.dumps({"lines": [{"span_id": span_id}]}).encode(),
    )
    evidence_relative = Path("evidence") / f"{page_number:06d}"
    _write_bytes(root / evidence_relative / "raw-native.txt", b"text\n")
    _write_bytes(root / evidence_relative / "normalized.txt", b"text\n")
    _write_bytes(root / evidence_relative / "model.jpg", b"jpeg")
    _write_bytes(
        root / evidence_relative / "evidence.json",
        json.dumps(
            {"probe": {"package_path": probe_relative.as_posix(), "route": "native"}}
        ).encode(),
    )
    return {
        "page_id": page_id,
        "pdf_page": page_number,
        "state": "ready",
        "package_path": evidence_relative.as_posix(),
        "model_input_bytes": 100,
    }


def _failed_page(page_number: int) -> dict[str, object]:
    source_sha256 = "a" * 64
    return {
        "page_id": f"sha256:{source_sha256}:page:{page_number:06d}",
        "pdf_page": page_number,
        "state": "failed",
        "package_path": None,
        "model_input_bytes": 0,
    }


def test_build_bundles_skips_a_chunk_where_every_page_failed(tmp_path: Path) -> None:
    """Regression test for F5: a fully-failed page chunk got written as a hollow,
    0-byte bundle. `transcribe` reported bundles created for a page range that
    carried no transcribed content at all.
    """
    document = {
        "catalog_key": "volume-01",
        "source_sha256": "a" * 64,
        "pages": [_ready_page(tmp_path, 1), _failed_page(2), _ready_page(tmp_path, 3)],
    }

    records, created, reused = _build_bundles(
        document,
        root=tmp_path,
        configuration={"sha256": "b" * 64},
        max_pages=1,
        max_bytes=8 * 1024 * 1024,
    )

    assert [record["sequence"] for record in records] == [1, 2]
    assert [record["start_pdf_page"] for record in records] == [1, 3]
    assert all(record["input_bytes"] > 0 for record in records)
    assert created == 2
    assert reused == 0


def test_build_bundles_never_mixes_failed_pages_into_multi_page_bundle(
    tmp_path: Path,
) -> None:
    """Failed pages must not produce bundles with unreadable null evidence paths."""
    document = {
        "catalog_key": "volume-01",
        "source_sha256": "a" * 64,
        "pages": [_ready_page(tmp_path, 1), _failed_page(2), _ready_page(tmp_path, 3)],
    }

    records, created, reused = _build_bundles(
        document,
        root=tmp_path,
        configuration={"sha256": "b" * 64},
        max_pages=10,
        max_bytes=8 * 1024 * 1024,
    )

    assert [record["sequence"] for record in records] == [1, 2]
    assert [(record["start_pdf_page"], record["end_pdf_page"]) for record in records] == [
        (1, 1),
        (3, 3),
    ]
    assert created == 2
    assert reused == 0


def test_validate_document_bundles_tolerates_a_gap_over_failed_pages_only(
    tmp_path: Path,
) -> None:
    pages = [_ready_page(tmp_path, 1), _failed_page(2), _ready_page(tmp_path, 3)]
    records, _, _ = _build_bundles(
        {"catalog_key": "volume-01", "source_sha256": "a" * 64, "pages": pages},
        root=tmp_path,
        configuration={"sha256": "b" * 64},
        max_pages=1,
        max_bytes=8 * 1024 * 1024,
    )

    _validate_document_bundles({"pages": pages, "bundles": records})

    not_actually_failed = [dict(pages[0]), {**pages[1], "state": "ready"}, dict(pages[2])]
    with pytest.raises(TranscriptionError, match="gap"):
        _validate_document_bundles({"pages": not_actually_failed, "bundles": records})


def test_validate_document_bundles_rejects_uncovered_ready_page_without_probe() -> None:
    """Bundle coverage must be checked even when no page-probe is available."""
    pages = [
        _failed_page(1),
        {**_failed_page(2), "state": "ready", "package_path": "evidence/2"},
    ]
    with pytest.raises(TranscriptionError, match="cover every document page"):
        _validate_document_bundles({"pages": pages, "bundles": []})


def _native_pdf(text: bytes) -> bytes:
    stream = b"BT /F1 18 Tf 72 720 Td (" + text + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{index} 0 obj\n".encode())
        payload.extend(value)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref).encode()
        + b"\n%%EOF\n"
    )
    return bytes(payload)
