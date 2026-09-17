"""Pinned native-text and rendering adapters for page evidence."""

from __future__ import annotations

import csv
import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from docling_parse.pdf_parser import ContentConfig, DoclingPdfParser

from cadgpt_regulations.errors import TranscriptionError
from cadgpt_regulations.jsonio import JsonObject, load_object
from cadgpt_regulations.storage import read_regular_snapshot

_TOOL_TIMEOUT_SECONDS = 30
_READ_CHUNK_SIZE = 1024 * 1024
_PINNED_TESSERACT_VERSION = "tesseract 5.3.4"
_PINNED_TESSDATA_BEST = {
    "eng": "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba",
    "fas": "99e420969b5ddd2cb135b416316a7ed417c59c4faf9e0d28941348f6448114df",
    "osd": "9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff",
}


@dataclass(frozen=True)
class ProbeWorkerOutput:
    """Native layout and pixels returned by one crash-isolated page worker."""

    native: JsonObject
    render: bytes
    render_metrics: JsonObject


@dataclass(frozen=True)
class OcrOutput:
    """Deterministic token and line records from pinned Tesseract TSV output."""

    tokens: list[JsonObject]
    lines: list[JsonObject]
    raw_text: str


def run_probe_worker(
    source: Path,
    *,
    page_number: int,
    page_id: str,
    dpi: int,
    output_directory: Path,
    timeout_seconds: int,
) -> ProbeWorkerOutput:
    """Probe one page in a bounded subprocess so native crashes stay terminal."""
    command = [
        sys.executable,
        "-m",
        "cadgpt_regulations.page_worker",
        "probe",
        "--source",
        str(source),
        "--page",
        str(page_number),
        "--page-id",
        page_id,
        "--dpi",
        str(dpi),
        "--output",
        str(output_directory),
    ]
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
            env=_worker_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise TranscriptionError(
            f"page worker timed out after {timeout_seconds} seconds"
        ) from exc
    except OSError as exc:
        raise TranscriptionError(
            f"page worker could not start: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        diagnostic = _bounded_diagnostic(completed.stderr)
        if completed.returncode < 0:
            raise TranscriptionError(
                f"page worker terminated by signal {-completed.returncode}: {diagnostic}"
            )
        raise TranscriptionError(f"page worker exited {completed.returncode}: {diagnostic}")
    result_path = output_directory / "result.json"
    native_path = output_directory / "native.json"
    render_path = output_directory / "render.png"
    for path in (result_path, native_path, render_path):
        read_regular_snapshot(path)
    result = load_object(result_path, description="page worker result")
    native = load_object(native_path, description="native page layout")
    try:
        render = render_path.read_bytes()
    except OSError as exc:
        raise TranscriptionError(
            f"cannot read page worker render: {type(exc).__name__}"
        ) from exc
    metrics = result.get("render_metrics")
    if not isinstance(metrics, dict):
        raise TranscriptionError("page worker result lacks render metrics")
    return ProbeWorkerOutput(
        native=native,
        render=render,
        render_metrics=cast(JsonObject, metrics),
    )


def runtime_toolchain(
    tessdata_directory: Path | None = None, *, require_ocr: bool = False
) -> JsonObject:
    """Describe the exact parser, renderer, image, and optional OCR runtime."""
    tesseract_version = _command_version(["tesseract", "--version"])
    models: list[JsonObject] = []
    if tessdata_directory is not None:
        for language in ("fas", "eng", "osd"):
            model = tessdata_directory / f"{language}.traineddata"
            if model.is_file() and not model.is_symlink():
                digest, byte_size = hash_regular_file(model)
                models.append(
                    {
                        "language": language,
                        "sha256": digest,
                        "bytes": byte_size,
                    }
                )
    if require_ocr:
        if tesseract_version != _PINNED_TESSERACT_VERSION:
            raise TranscriptionError(f"OCR requires exactly {_PINNED_TESSERACT_VERSION}")
        actual = {
            cast(str, model["language"]): cast(str, model["sha256"]) for model in models
        }
        if actual != _PINNED_TESSDATA_BEST:
            raise TranscriptionError(
                "OCR requires pinned tessdata_best fas, eng, and osd models"
            )
    return {
        "docling_parse": _package_version("docling-parse"),
        "pypdfium2": _package_version("pypdfium2"),
        "pillow": _package_version("Pillow"),
        "tesseract": tesseract_version,
        "tessdata_models": models,
    }


def run_tesseract_tsv(
    image: Path,
    *,
    page_id: str,
    tessdata_directory: Path,
    dpi: int,
    page_segmentation_mode: int,
    timeout_seconds: int,
) -> OcrOutput:
    """Run pinned Persian/English OCR and parse its TSV without shell mediation."""
    read_regular_snapshot(image)
    command = [
        "tesseract",
        str(image),
        "stdout",
        "--tessdata-dir",
        str(tessdata_directory),
        "-l",
        "fas+eng",
        "--dpi",
        str(dpi),
        "--psm",
        str(page_segmentation_mode),
        "-c",
        "tessedit_create_tsv=1",
    ]
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
            env=_worker_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise TranscriptionError(f"OCR timed out after {timeout_seconds} seconds") from exc
    except OSError as exc:
        raise TranscriptionError(f"OCR could not start: {type(exc).__name__}") from exc
    if completed.returncode != 0:
        raise TranscriptionError(
            f"OCR exited {completed.returncode}: {_bounded_diagnostic(completed.stderr)}"
        )
    return _parse_tesseract_tsv(
        completed.stdout.decode("utf-8", errors="strict"), page_id=page_id
    )


def hash_regular_file(path: Path) -> tuple[str, int]:
    """Hash one stable regular file without following a final symlink."""
    try:
        before = path.lstat()
    except OSError as exc:
        raise TranscriptionError(f"cannot inspect {path}: {exc}") from exc
    if path.is_symlink() or not path.is_file() or before.st_nlink != 1:
        raise TranscriptionError(f"path is not a single-link regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise TranscriptionError(f"cannot open {path}: {exc}") from exc
    digest = hashlib.sha256()
    byte_size = 0
    try:
        opened = os.fstat(descriptor)
        while chunk := os.read(descriptor, _READ_CHUNK_SIZE):
            digest.update(chunk)
            byte_size += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or byte_size != after.st_size:
        raise TranscriptionError(f"file changed while it was read: {path}")
    return digest.hexdigest(), byte_size


class PageSource:
    """Read native layout and fixed-resolution pixels from one attested PDF."""

    def __init__(self, path: Path) -> None:
        self._path = path
        try:
            self._docling_parser = DoclingPdfParser(loglevel="fatal")
            self._docling_document = self._docling_parser.load(
                path,
                lazy=True,
                content_config=ContentConfig(include_bitmap_bytes=False),
            )
            self._pdfium_document = pdfium.PdfDocument(path)
        except Exception as exc:
            raise TranscriptionError(
                f"cannot open PDF {path}: {type(exc).__name__}"
            ) from exc

    def close(self) -> None:
        self._docling_document.unload()
        self._pdfium_document.close()

    def __enter__(self) -> PageSource:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def native_page(self, page_number: int, *, page_id: str) -> JsonObject:
        """Return raw-preserving positioned native cells using integer milli-points."""
        try:
            page = self._docling_document.get_page(page_number)
        except Exception as exc:
            raise TranscriptionError(
                f"native parse failed for {self._path.name} page {page_number}: "
                f"{type(exc).__name__}"
            ) from exc

        chars = [
            _cell_record(cell, page_id=page_id, kind="char", index=index)
            for index, cell in enumerate(page.char_cells)
        ]
        words = [
            _cell_record(cell, page_id=page_id, kind="word", index=index)
            for index, cell in enumerate(page.word_cells)
        ]
        lines = [
            _cell_record(cell, page_id=page_id, kind="line", index=index)
            for index, cell in enumerate(page.textline_cells)
        ]
        rect = page.dimension.rect
        width_mpt = _mpt(
            max(rect.r_x0, rect.r_x1, rect.r_x2, rect.r_x3)
            - min(rect.r_x0, rect.r_x1, rect.r_x2, rect.r_x3)
        )
        height_mpt = _mpt(
            max(rect.r_y0, rect.r_y1, rect.r_y2, rect.r_y3)
            - min(rect.r_y0, rect.r_y1, rect.r_y2, rect.r_y3)
        )
        bitmap_area_mpt2 = sum(
            _rect_area_mpt2(bitmap.rect) for bitmap in page.bitmap_resources
        )
        page_area_mpt2 = max(1, width_mpt * height_mpt)
        bitmap_coverage_permyriad = min(
            10_000, (bitmap_area_mpt2 * 10_000) // page_area_mpt2
        )
        raw_glyph_text = "".join(cast(str, cell["raw_text"]) for cell in chars)
        return {
            "schema_version": "1.0.0",
            "page_id": page_id,
            "coordinate_space": {
                "unit": "pdf_millipoint",
                "origin": "bottom_left",
                "width": width_mpt,
                "height": height_mpt,
                "rotation_millidegrees": _mpt(page.dimension.angle),
            },
            "raw_glyph_text": raw_glyph_text,
            "raw_line_text": [cast(str, line["raw_text"]) for line in lines],
            "chars": chars,
            "words": words,
            "lines": lines,
            "resource_counts": {
                "bitmaps": len(page.bitmap_resources),
                "shapes": len(page.shapes),
                "widgets": len(page.widgets),
                "hyperlinks": len(page.hyperlinks),
            },
            "bitmap_coverage_permyriad": bitmap_coverage_permyriad,
        }

    def render_png(self, page_number: int, *, dpi: int) -> tuple[bytes, JsonObject]:
        """Render one page to deterministic RGB PNG bytes and integer pixel metrics."""
        try:
            page = self._pdfium_document[page_number - 1]
            bitmap = page.render(scale=dpi / 72, may_draw_forms=False)
            image = bitmap.to_pil().convert("RGB")
            bitmap.close()
            page.close()
        except Exception as exc:
            raise TranscriptionError(
                f"render failed for {self._path.name} page {page_number}: "
                f"{type(exc).__name__}"
            ) from exc

        grayscale = image.convert("L")
        histogram = grayscale.histogram()
        total_pixels = image.width * image.height
        nonwhite_pixels = sum(histogram[:245])
        ink_coverage_permyriad = (
            (nonwhite_pixels * 10_000) // total_pixels if total_pixels else 0
        )
        output = BytesIO()
        image.save(output, format="PNG", optimize=False, compress_level=9)
        return output.getvalue(), {
            "width_pixels": image.width,
            "height_pixels": image.height,
            "ink_coverage_permyriad": ink_coverage_permyriad,
        }


def _cell_record(cell: Any, *, page_id: str, kind: str, index: int) -> JsonObject:
    rect = cell.rect
    xs = [rect.r_x0, rect.r_x1, rect.r_x2, rect.r_x3]
    ys = [rect.r_y0, rect.r_y1, rect.r_y2, rect.r_y3]
    raw_text = cast(str, cell.orig)
    return {
        "span_id": f"{page_id}:native:{kind}:{index:06d}",
        "source_index": cast(int, cell.index),
        "raw_text": raw_text,
        "text": cast(str, cell.text),
        "quad": [
            _mpt(rect.r_x0),
            _mpt(rect.r_y0),
            _mpt(rect.r_x1),
            _mpt(rect.r_y1),
            _mpt(rect.r_x2),
            _mpt(rect.r_y2),
            _mpt(rect.r_x3),
            _mpt(rect.r_y3),
        ],
        "bbox": [_mpt(min(xs)), _mpt(min(ys)), _mpt(max(xs)), _mpt(max(ys))],
        "direction": cell.text_direction.value,
        "confidence_permyriad": max(0, min(10_000, _mpt(cell.confidence * 10))),
        "font_key": cast(str | None, cell.font_key),
        "font_name": cast(str | None, cell.font_name),
    }


def _rect_area_mpt2(rect: Any) -> int:
    width = _mpt(
        max(rect.r_x0, rect.r_x1, rect.r_x2, rect.r_x3)
        - min(rect.r_x0, rect.r_x1, rect.r_x2, rect.r_x3)
    )
    height = _mpt(
        max(rect.r_y0, rect.r_y1, rect.r_y2, rect.r_y3)
        - min(rect.r_y0, rect.r_y1, rect.r_y2, rect.r_y3)
    )
    return max(0, width) * max(0, height)


def _mpt(value: float) -> int:
    return round(value * 1000)


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError as exc:
        raise TranscriptionError(f"required package is not installed: {name}") from exc


def _command_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=_TOOL_TIMEOUT_SECONDS,
            env={"LC_ALL": "C", "LANG": "C", "PATH": os.environ.get("PATH", "")},
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    return first_line.strip() or None


def _worker_environment() -> dict[str, str]:
    return {
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
    }


def _bounded_diagnostic(value: bytes, *, limit: int = 600) -> str:
    text = value.decode("utf-8", errors="replace").strip()
    if not text:
        return "no diagnostic"
    return " ".join(text.split())[:limit]


def _parse_tesseract_tsv(value: str, *, page_id: str) -> OcrOutput:
    reader = csv.DictReader(value.splitlines(), delimiter="\t")
    expected = {
        "level",
        "page_num",
        "block_num",
        "par_num",
        "line_num",
        "word_num",
        "left",
        "top",
        "width",
        "height",
        "conf",
        "text",
    }
    if reader.fieldnames is None or set(reader.fieldnames) != expected:
        raise TranscriptionError("OCR returned an unexpected TSV header")
    tokens: list[JsonObject] = []
    grouped: dict[tuple[int, int, int], list[JsonObject]] = {}
    for row in reader:
        text = row["text"]
        if row["level"] != "5" or not text.strip():
            continue
        try:
            left = int(row["left"])
            top = int(row["top"])
            width = int(row["width"])
            height = int(row["height"])
            confidence = float(row["conf"])
            key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        except (TypeError, ValueError) as exc:
            raise TranscriptionError("OCR returned a malformed TSV row") from exc
        token: JsonObject = {
            "span_id": f"{page_id}:ocr:word:{len(tokens):06d}",
            "raw_text": text,
            "bbox": [left, top, left + width, top + height],
            "confidence_permyriad": max(0, min(10_000, round(confidence * 100))),
            "block": key[0],
            "paragraph": key[1],
            "line": key[2],
        }
        tokens.append(token)
        grouped.setdefault(key, []).append(token)
    lines: list[JsonObject] = []
    for line_tokens in grouped.values():
        boxes = [cast(list[int], token["bbox"]) for token in line_tokens]
        text = " ".join(cast(str, token["raw_text"]) for token in line_tokens)
        lines.append(
            {
                "span_id": f"{page_id}:ocr:line:{len(lines):06d}",
                "raw_text": text,
                "bbox": [
                    min(box[0] for box in boxes),
                    min(box[1] for box in boxes),
                    max(box[2] for box in boxes),
                    max(box[3] for box in boxes),
                ],
                "confidence_permyriad": sum(
                    cast(int, token["confidence_permyriad"]) for token in line_tokens
                )
                // len(line_tokens),
                "token_span_ids": [token["span_id"] for token in line_tokens],
            }
        )
    return OcrOutput(
        tokens=tokens,
        lines=lines,
        raw_text="\n".join(cast(str, line["raw_text"]) for line in lines),
    )
