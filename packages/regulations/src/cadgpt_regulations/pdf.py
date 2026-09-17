"""Content probing and authoritative PDF metadata extraction."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

PDFINFO_TIMEOUT_SECONDS = 60
_PAGES_PATTERN = re.compile(r"^Pages:\s+(\d+)\s*$", re.MULTILINE)
_ENCRYPTED_PATTERN = re.compile(r"^Encrypted:\s+yes(?:\s|$)", re.MULTILINE)


@dataclass(frozen=True)
class PdfProbe:
    page_count: int | None
    encrypted: bool
    error_code: str | None
    diagnostic: str | None


def detect_media_type(prefix: bytes) -> str:
    """Use signatures and markup, never the filename suffix."""
    if b"%PDF-" in prefix[:1024]:
        return "application/pdf"
    normalized = prefix.lstrip().lower()
    if normalized.startswith(b"<!doctype html") or normalized.startswith(b"<html"):
        return "text/html"
    if b"<html" in normalized[:4096]:
        return "text/html"
    return "application/octet-stream"


def inspect_pdf(path: Path) -> PdfProbe:
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    try:
        completed = subprocess.run(  # noqa: S603
            ["pdfinfo", str(path.absolute())],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
            timeout=PDFINFO_TIMEOUT_SECONDS,
            env=environment,
        )
    except FileNotFoundError:
        return PdfProbe(None, False, "PDFINFO_UNAVAILABLE", "pdfinfo executable not found")
    except subprocess.TimeoutExpired:
        return PdfProbe(
            None,
            False,
            "PDFINFO_FAILED",
            f"pdfinfo exceeded {PDFINFO_TIMEOUT_SECONDS} seconds",
        )
    except OSError as exc:
        return PdfProbe(None, False, "PDFINFO_FAILED", _stable_os_diagnostic(exc))

    combined = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part
    )
    if completed.returncode != 0:
        return PdfProbe(
            None,
            False,
            "PDFINFO_FAILED",
            combined or f"pdfinfo exited with status {completed.returncode}",
        )
    if _ENCRYPTED_PATTERN.search(completed.stdout):
        return PdfProbe(None, True, "PDF_ENCRYPTED", "pdfinfo reports an encrypted PDF")
    pages = _PAGES_PATTERN.search(completed.stdout)
    if pages is None:
        return PdfProbe(
            None, False, "PDFINFO_FAILED", "pdfinfo did not report a page count"
        )
    return PdfProbe(int(pages.group(1)), False, None, None)


def _stable_os_diagnostic(exc: OSError) -> str:
    return f"{type(exc).__name__}: {exc.strerror or 'operating system error'}"
