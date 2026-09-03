from __future__ import annotations

import stat
from pathlib import Path

import pytest
from cadgpt_regulations.errors import TranscriptionError
from cadgpt_regulations.page_tools import run_probe_worker
from cadgpt_regulations.store_index import validate_output_inventory
from cadgpt_regulations.transcription import ascii_digit_view, normalize_search_text


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
