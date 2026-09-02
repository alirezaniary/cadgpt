from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


def _write_minimal_pdf(path: Path, pages: int = 1) -> None:
    """Write a small standards-compliant PDF so tests exercise real pdfinfo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{index + 3} 0 R" for index in range(pages))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode())
    objects.extend(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] >>" for _ in range(pages)
    )

    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode())
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    path.write_bytes(document)


@pytest.fixture
def write_pdf() -> Callable[[Path, int], None]:
    return _write_minimal_pdf
