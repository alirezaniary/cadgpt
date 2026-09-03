"""Lossless text normalization, pinned OCR, evidence packages, and model bundles."""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import unicodedata
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from itertools import pairwise
from pathlib import Path
from typing import cast

from PIL import Image

from cadgpt_regulations.errors import ManifestError, TranscriptionError
from cadgpt_regulations.jsonio import (
    JsonObject,
    canonical_bytes,
    loads_object,
    sha256_json,
    validate_schema,
)
from cadgpt_regulations.page_probe import validate_page_probe
from cadgpt_regulations.page_tools import OcrOutput, run_tesseract_tsv, runtime_toolchain
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.storage import (
    InstallStatus,
    StorageError,
    ensure_private_tree,
    install_immutable_bytes,
    install_terminal_directory,
    make_temporary_directory,
    read_attested_bytes,
    safe_path,
    snapshot_directory,
    validate_output_root,
)
from cadgpt_regulations.store_index import validate_output_inventory

TRANSCRIPTION_SCHEMA_VERSION = "1.0.0"
NORMALIZATION_VERSION = "1.0.0"
DEFAULT_OCR_TIMEOUT_SECONDS = 180
DEFAULT_BUNDLE_MAX_PAGES = 10
DEFAULT_BUNDLE_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_MODEL_MAX_EDGE = 1600
DEFAULT_MODEL_JPEG_QUALITY = 82

_PRESENTATION_RANGES = ((0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
_DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_EQUATION_MARKERS = re.compile(r"[=≤≥≠≈±×÷√∑∫^²³₀-₉]")  # noqa: RUF001
_ABBREVIATION_PATTERN = re.compile(r"(?<![A-Za-z])(LRFD|ASD)(?![A-Za-z])")
_UNIT_PATTERN = re.compile(
    r"(?<!\w)(?:mm|cm|m|m2|m3|kN|N|MPa|Pa|kg|s|Hz|°C)(?!\w)|"
    r"(?:میلی[‌ ]?متر|سانتی[‌ ]?متر|کیلو[‌ ]?نیوتن|مگاپاسکال|متر(?:مربع|مکعب)?)"
)
_PRINTED_LABEL_PATTERN = re.compile(
    r"^[\s\-–—()\[\]۰-۹٠-٩0-9ivxlcdmIVXLCDM]{1,24}$"  # noqa: RUF001
)
_SENTENCE_ENDINGS = frozenset(".؟?!؛;:…")


@dataclass(frozen=True)
class TranscriptionRun:
    manifest: JsonObject
    packages_created: int
    packages_reused: int
    bundles_created: int
    bundles_reused: int
    manifest_created: bool
    manifest_path: Path


@dataclass(frozen=True)
class _PreparedPage:
    record: JsonObject
    normalized_text: str


def normalize_search_text(value: str) -> tuple[str, JsonObject]:
    """Derive searchable Persian text while preserving source mathematics and digits."""
    presentation_changes = 0
    normalized_characters: list[str] = []
    for character in value:
        codepoint = ord(character)
        if any(start <= codepoint <= end for start, end in _PRESENTATION_RANGES):
            replacement = unicodedata.normalize("NFKC", character)
            presentation_changes += int(replacement != character)
            normalized_characters.append(replacement)
        else:
            normalized_characters.append(character)
    normalized = "".join(normalized_characters)
    yeh_changes = normalized.count("ي")
    kaf_changes = normalized.count("ك")
    normalized = normalized.replace("ي", "ی").replace("ك", "ک")
    cleaned_lines: list[str] = []
    whitespace_changes = 0
    for line in normalized.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = " ".join(line.replace("\t", " ").split())
        whitespace_changes += int(cleaned != line)
        cleaned_lines.append(cleaned)
    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()
        whitespace_changes += 1
    result = "\n".join(cleaned_lines)
    log: JsonObject = {
        "version": NORMALIZATION_VERSION,
        "operations": [
            {
                "name": "arabic_presentation_forms_nfkc",
                "changes": presentation_changes,
            },
            {"name": "persian_yeh_mapping", "changes": yeh_changes},
            {"name": "persian_kaf_mapping", "changes": kaf_changes},
            {
                "name": "horizontal_whitespace_cleanup",
                "changes": whitespace_changes,
            },
        ],
        "protected_views": [
            "source_digits",
            "operators",
            "signs",
            "decimal_separators",
            "superscripts",
            "clause_identifiers",
        ],
    }
    return result, log


def ascii_digit_view(value: str) -> str:
    """Return a separate ASCII-digit search view without changing source text."""
    return value.translate(_DIGIT_TRANSLATION)


def build_transcription(
    probe: JsonObject,
    *,
    root: Path,
    tessdata_directory: Path | None,
    workers: int = 1,
    ocr_timeout_seconds: int = DEFAULT_OCR_TIMEOUT_SECONDS,
    bundle_max_pages: int = DEFAULT_BUNDLE_MAX_PAGES,
    bundle_max_bytes: int = DEFAULT_BUNDLE_MAX_BYTES,
    model_max_edge: int = DEFAULT_MODEL_MAX_EDGE,
    model_jpeg_quality: int = DEFAULT_MODEL_JPEG_QUALITY,
) -> TranscriptionRun:
    """Transcribe every terminal probe record and build bounded ordered bundles."""
    try:
        validate_output_root(root)
    except StorageError as exc:
        raise TranscriptionError(str(exc)) from exc
    validate_page_probe(probe, root=root)
    _validate_configuration(
        workers=workers,
        ocr_timeout_seconds=ocr_timeout_seconds,
        bundle_max_pages=bundle_max_pages,
        bundle_max_bytes=bundle_max_bytes,
        model_max_edge=model_max_edge,
        model_jpeg_quality=model_jpeg_quality,
    )
    probe_documents = cast(list[JsonObject], probe["documents"])
    ocr_required = any(
        page["route"] in {"ocr", "native_plus_ocr"}
        for document in probe_documents
        for page in cast(list[JsonObject], document["pages"])
    )
    ocr_toolchain_error: str | None = None
    ocr_toolchain: JsonObject | None = None
    if ocr_required:
        try:
            if tessdata_directory is None:
                raise TranscriptionError("OCR pages require an explicit tessdata directory")
            ocr_toolchain = runtime_toolchain(tessdata_directory, require_ocr=True)
            if ocr_toolchain != probe["toolchain"]:
                raise TranscriptionError(
                    "OCR runtime differs from the page probe toolchain identity"
                )
        except TranscriptionError as exc:
            ocr_toolchain_error = str(exc)

    configuration_values: JsonObject = {
        "schema_version": "1.0.0",
        "normalization_version": NORMALIZATION_VERSION,
        "ocr_timeout_seconds": ocr_timeout_seconds,
        "ocr_languages": ["fas", "eng"],
        "ocr_primary_psm": 3,
        "ocr_dense_fallback_psm": 6,
        "ocr_general_review_confidence_permyriad": 6000,
        "ocr_critical_review_confidence_permyriad": 7500,
        "bundle_max_pages": bundle_max_pages,
        "bundle_max_bytes": bundle_max_bytes,
        "model_max_edge": model_max_edge,
        "model_jpeg_quality": model_jpeg_quality,
    }
    configuration: JsonObject = {
        **configuration_values,
        "sha256": sha256_json(configuration_values),
    }
    documents: list[JsonObject] = []
    packages_created = 0
    packages_reused = 0
    bundles_created = 0
    bundles_reused = 0
    for document in probe_documents:
        transcribed, created, reused = _transcribe_document(
            document,
            root=root,
            probe=probe,
            configuration=configuration,
            tessdata_directory=tessdata_directory,
            ocr_toolchain=ocr_toolchain,
            ocr_toolchain_error=ocr_toolchain_error,
            workers=workers,
        )
        bundles, bundle_created, bundle_reused = _build_bundles(
            transcribed,
            root=root,
            configuration=configuration,
            max_pages=bundle_max_pages,
            max_bytes=bundle_max_bytes,
        )
        transcribed["bundles"] = bundles
        documents.append(transcribed)
        packages_created += created
        packages_reused += reused
        bundles_created += bundle_created
        bundles_reused += bundle_reused
    pages = [
        page for document in documents for page in cast(list[JsonObject], document["pages"])
    ]
    bundles = [
        bundle
        for document in documents
        for bundle in cast(list[JsonObject], document["bundles"])
    ]
    summary = _summarize(pages, bundles, documents)
    probe_payload = canonical_bytes(probe)
    manifest: JsonObject = {
        "schema_version": TRANSCRIPTION_SCHEMA_VERSION,
        "catalog": probe["catalog"],
        "acquisition": probe["acquisition"],
        "probe": {
            "sha256": hashlib.sha256(probe_payload).hexdigest(),
            "configuration_sha256": cast(JsonObject, probe["configuration"])["sha256"],
            "toolchain_sha256": probe["toolchain_sha256"],
        },
        "configuration": configuration,
        "ocr_toolchain": ocr_toolchain,
        "documents": documents,
        "summary": summary,
    }
    validate_transcription(manifest, root=root, probe=probe)
    manifest_path, manifest_created = _install_manifest(root, manifest)
    validate_output_inventory(root)
    return TranscriptionRun(
        manifest=manifest,
        packages_created=packages_created,
        packages_reused=packages_reused,
        bundles_created=bundles_created,
        bundles_reused=bundles_reused,
        manifest_created=manifest_created,
        manifest_path=manifest_path,
    )


def _validate_configuration(
    *,
    workers: int,
    ocr_timeout_seconds: int,
    bundle_max_pages: int,
    bundle_max_bytes: int,
    model_max_edge: int,
    model_jpeg_quality: int,
) -> None:
    if workers < 1:
        raise TranscriptionError("transcription workers must be at least one")
    if not 1 <= ocr_timeout_seconds <= 3600:
        raise TranscriptionError("OCR timeout must be between 1 and 3600 seconds")
    if not 1 <= bundle_max_pages <= 10:
        raise TranscriptionError("bundle maximum pages must be between 1 and 10")
    if bundle_max_bytes < 1024:
        raise TranscriptionError("bundle byte ceiling must be at least 1024")
    if not 320 <= model_max_edge <= 4096:
        raise TranscriptionError("model image edge must be between 320 and 4096 pixels")
    if not 30 <= model_jpeg_quality <= 95:
        raise TranscriptionError("model JPEG quality must be between 30 and 95")


def _transcribe_document(
    document: JsonObject,
    *,
    root: Path,
    probe: JsonObject,
    configuration: JsonObject,
    tessdata_directory: Path | None,
    ocr_toolchain: JsonObject | None,
    ocr_toolchain_error: str | None,
    workers: int,
) -> tuple[JsonObject, int, int]:
    probe_pages = cast(list[JsonObject], document["pages"])
    prepared: list[_PreparedPage] = []
    created = 0
    reused = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures: dict[int, Future[tuple[_PreparedPage, bool]]] = {}
        for page in probe_pages:
            page_number = cast(int, page["pdf_page"])
            try:
                futures[page_number] = executor.submit(
                    _transcribe_page,
                    page,
                    document=document,
                    root=root,
                    probe=probe,
                    configuration=configuration,
                    tessdata_directory=tessdata_directory,
                    ocr_toolchain=ocr_toolchain,
                    ocr_toolchain_error=ocr_toolchain_error,
                )
            except Exception as exc:  # noqa: BLE001 - every page must become terminal
                prepared.append(_failed_prepared(page, "TRANSCRIPTION_SUBMIT_FAILED", exc))
        by_page = {cast(int, item.record["pdf_page"]): item for item in prepared}
        for page in probe_pages:
            page_number = cast(int, page["pdf_page"])
            future = futures.get(page_number)
            if future is None:
                continue
            try:
                prepared_result, was_created = future.result()
            except Exception as exc:  # noqa: BLE001 - isolate all worker failures
                prepared_result = _failed_prepared(page, "PAGE_TRANSCRIPTION_FAILED", exc)
            else:
                if was_created:
                    created += 1
                else:
                    reused += 1
            by_page[page_number] = prepared_result
        prepared = [by_page[cast(int, page["pdf_page"])] for page in probe_pages]
    document_result: JsonObject = {
        "catalog_key": document["catalog_key"],
        "catalog_order": document["catalog_order"],
        "source_sha256": document["source_sha256"],
        "source_bytes": document["source_bytes"],
        "pdf_page_count": document["pdf_page_count"],
        "artifact_path": document["artifact_path"],
        "pages": [item.record for item in prepared],
        "bundles": [],
    }
    return document_result, created, reused


def _transcribe_page(
    page: JsonObject,
    *,
    document: JsonObject,
    root: Path,
    probe: JsonObject,
    configuration: JsonObject,
    tessdata_directory: Path | None,
    ocr_toolchain: JsonObject | None,
    ocr_toolchain_error: str | None,
) -> tuple[_PreparedPage, bool]:
    page_number = cast(int, page["pdf_page"])
    page_id = cast(str, page["page_id"])
    if page["state"] == "failed":
        error = cast(JsonObject, page["error"])
        terminal_record = _failed_record(
            page,
            "PROBE_PAGE_FAILED",
            f"{error['code']}: {error['diagnostic']}",
        )
        return _PreparedPage(terminal_record, ""), False
    package_relative = (
        Path("transcriptions")
        / cast(str, document["source_sha256"])
        / cast(str, cast(JsonObject, probe["configuration"])["sha256"])
        / cast(str, probe["toolchain_sha256"])
        / cast(str, configuration["sha256"])
        / f"{page_number:06d}"
    )
    existing = _existing_transcription_record(
        root, package_relative, page_id=page_id, pdf_page=page_number
    )
    if existing is not None:
        return existing, False
    package = safe_path(root, cast(str, page["package_path"]))
    page_payload, _ = read_attested_bytes(
        safe_path(package, "page.json"),
        expected_sha256=cast(str, page["package_sha256"]),
    )
    package_record = loads_object(page_payload.decode("utf-8"), description="page package")
    artifact_by_role = {
        cast(str, artifact["role"]): artifact
        for artifact in cast(list[JsonObject], package_record["artifacts"])
    }
    native_artifact = artifact_by_role["native_layout"]
    render_artifact = artifact_by_role["source_render"]
    native_payload, _ = read_attested_bytes(
        safe_path(root, cast(str, native_artifact["path"])),
        expected_sha256=cast(str, native_artifact["sha256"]),
        expected_bytes=cast(int, native_artifact["bytes"]),
    )
    render_payload, _ = read_attested_bytes(
        safe_path(root, cast(str, render_artifact["path"])),
        expected_sha256=cast(str, render_artifact["sha256"]),
        expected_bytes=cast(int, render_artifact["bytes"]),
    )
    native = loads_object(native_payload.decode("utf-8"), description="native layout")
    raw_native = cast(str, native["raw_glyph_text"])
    native_search = "\n".join(cast(list[str], native["raw_line_text"]))
    normalized_native, native_log = normalize_search_text(native_search)
    route = cast(str, page["route"])
    ocr: JsonObject | None = None
    ocr_input: bytes | None = None
    normalized_ocr = ""
    ocr_log: JsonObject | None = None
    review_flags: list[str] = []
    if route in {"ocr", "native_plus_ocr"}:
        if ocr_toolchain_error is not None:
            raise TranscriptionError(ocr_toolchain_error)
        if tessdata_directory is None or ocr_toolchain is None:
            raise TranscriptionError("OCR toolchain is unavailable")
        preprocessing = _ocr_preprocessing(
            render_payload,
            catalog_key=cast(str, document["catalog_key"]),
            classification=cast(str, page["classification"]),
        )
        ocr_input, preprocessing_operations = preprocessing
        ocr_work = Path(tempfile.mkdtemp(prefix="cadgpt-ocr-"))
        ocr_work.chmod(0o700)
        try:
            ocr_input_path = ocr_work / "input.png"
            install_immutable_bytes(ocr_input_path, ocr_input)
            primary = run_tesseract_tsv(
                ocr_input_path,
                page_id=page_id,
                tessdata_directory=tessdata_directory,
                dpi=cast(int, cast(JsonObject, probe["configuration"])["render_dpi"]),
                page_segmentation_mode=3,
                timeout_seconds=cast(int, configuration["ocr_timeout_seconds"]),
            )
            attempts = [_ocr_attempt(primary, page_segmentation_mode=3)]
            ocr_output = primary
            selected_psm = 3
            if _needs_dense_fallback(primary):
                fallback = run_tesseract_tsv(
                    ocr_input_path,
                    page_id=page_id,
                    tessdata_directory=tessdata_directory,
                    dpi=cast(
                        int,
                        cast(JsonObject, probe["configuration"])["render_dpi"],
                    ),
                    page_segmentation_mode=6,
                    timeout_seconds=cast(int, configuration["ocr_timeout_seconds"]),
                )
                attempts.append(_ocr_attempt(fallback, page_segmentation_mode=6))
                if _ocr_score(fallback) > _ocr_score(primary):
                    ocr_output = fallback
                    selected_psm = 6
        finally:
            try:
                shutil.rmtree(ocr_work)
            except OSError as exc:
                raise TranscriptionError(
                    f"cannot clean OCR work directory: {type(exc).__name__}"
                ) from exc
        ocr = {
            "schema_version": "1.0.0",
            "page_id": page_id,
            "coordinate_space": {
                "unit": "pixel",
                "origin": "top_left",
                "width": cast(JsonObject, page["metrics"])["render_width_pixels"],
                "height": cast(JsonObject, page["metrics"])["render_height_pixels"],
            },
            "engine": {
                "name": "tesseract",
                "version": ocr_toolchain["tesseract"],
                "languages": ["fas", "eng"],
                "page_segmentation_mode": selected_psm,
                "dpi": cast(int, cast(JsonObject, probe["configuration"])["render_dpi"]),
                "models": ocr_toolchain["tessdata_models"],
                "attempts": attempts,
            },
            "preprocessing": {
                "source_render_sha256": render_artifact["sha256"],
                "operations": preprocessing_operations,
            },
            "raw_text": ocr_output.raw_text,
            "tokens": ocr_output.tokens,
            "lines": ocr_output.lines,
        }
        _validate_ocr(ocr, page_id=page_id)
        normalized_ocr, ocr_log = normalize_search_text(ocr_output.raw_text)
        confidences = [
            cast(int, token["confidence_permyriad"]) for token in ocr_output.tokens
        ]
        if not confidences:
            review_flags.append("OCR_NO_TEXT")
        elif min(confidences) < 6000:
            review_flags.append("OCR_LOW_CONFIDENCE_TOKENS")
        critical_tokens = [
            token
            for token in ocr_output.tokens
            if _critical_ocr_token(cast(str, token["raw_text"]))
            and cast(int, token["confidence_permyriad"]) < 7500
        ]
        if critical_tokens:
            review_flags.append("OCR_CRITICAL_IDENTIFIER_REVIEW")
        if document["catalog_key"] == "volume-17-edition-1403" and any(
            cast(int, token["confidence_permyriad"]) < 7500 for token in ocr_output.tokens
        ):
            review_flags.append("OCR_WATERMARK_OVERLAP_REVIEW")
        render_height = cast(int, cast(JsonObject, page["metrics"])["render_height_pixels"])
        if any(
            cast(list[int], token["bbox"])[1] > render_height * 7 // 10
            and cast(int, token["confidence_permyriad"]) < 7500
            for token in ocr_output.tokens
        ):
            review_flags.append("OCR_SIGNATURE_REGION_REVIEW")
    if route == "ocr":
        normalized = normalized_ocr
    elif route == "native_plus_ocr":
        normalized = "\n".join(
            value for value in (normalized_native, normalized_ocr) if value
        )
    else:
        normalized = normalized_native
    digit_view = ascii_digit_view(normalized)
    model_render = _model_render(
        render_payload,
        max_edge=cast(int, configuration["model_max_edge"]),
        quality=cast(int, configuration["model_jpeg_quality"]),
    )
    symbol_candidates, crop_files = _symbol_candidates(
        native,
        ocr,
        render_payload,
        page_id=page_id,
    )
    printed_page_label = _printed_page_label(native, ocr)
    table_candidates = _table_candidates(page, native)
    state = "needs_review" if page["state"] == "needs_review" or review_flags else "ready"
    reason_codes = list(cast(list[str], page["reason_codes"])) + review_flags
    files: dict[str, bytes] = {
        "raw-native.txt": raw_native.encode("utf-8"),
        "normalized.txt": normalized.encode("utf-8"),
        "digits-ascii.txt": digit_view.encode("utf-8"),
        "model.jpg": model_render,
    }
    if ocr is not None:
        files["ocr.json"] = canonical_bytes(ocr)
        assert ocr_input is not None
        files["ocr-input.png"] = ocr_input
    files.update(crop_files)
    artifacts = [
        _artifact_record(package_relative, name, payload)
        for name, payload in sorted(files.items())
    ]
    evidence: JsonObject = {
        "schema_version": "1.0.0",
        "page_id": page_id,
        "source": {
            "catalog_key": document["catalog_key"],
            "catalog_order": document["catalog_order"],
            "sha256": document["source_sha256"],
            "bytes": document["source_bytes"],
            "pdf_page_count": document["pdf_page_count"],
            "pdf_page": page_number,
            "printed_page_label": printed_page_label,
        },
        "probe": {
            "package_path": page["package_path"],
            "package_sha256": page["package_sha256"],
            "configuration_sha256": cast(JsonObject, probe["configuration"])["sha256"],
            "toolchain_sha256": probe["toolchain_sha256"],
            "classification": page["classification"],
            "route": route,
        },
        "configuration_sha256": configuration["sha256"],
        "state": state,
        "reason_codes": reason_codes,
        "normalization": {
            "native": native_log,
            "ocr": ocr_log,
            "combined_policy": route,
            "digit_view": "persian_and_arabic_indic_to_ascii",
        },
        "ocr": None
        if ocr is None
        else {
            "engine": ocr["engine"],
            "token_count": len(cast(list[JsonObject], ocr["tokens"])),
            "line_count": len(cast(list[JsonObject], ocr["lines"])),
        },
        "semantic_evidence": {
            "symbols": symbol_candidates,
            "tables": table_candidates,
        },
        "artifacts": artifacts,
        "error": None,
    }
    try:
        validate_schema(
            evidence,
            load_packaged_json("cadgpt_regulations.schemas", "page-evidence.schema.json"),
            description="page evidence",
        )
    except ManifestError as exc:
        raise TranscriptionError(str(exc)) from exc
    evidence_payload = canonical_bytes(evidence)
    files["evidence.json"] = evidence_payload
    was_created = _install_package(root, package_relative, files, "evidence.json")
    terminal_record = {
        "page_id": page_id,
        "pdf_page": page_number,
        "state": state,
        "classification": page["classification"],
        "route": route,
        "reason_codes": reason_codes,
        "printed_page_label": printed_page_label,
        "package_path": package_relative.as_posix(),
        "package_sha256": hashlib.sha256(evidence_payload).hexdigest(),
        "normalized_sha256": hashlib.sha256(files["normalized.txt"]).hexdigest(),
        "normalized_chars": len(normalized),
        "model_input_bytes": len(model_render) + len(files["normalized.txt"]),
        "error": None,
    }
    return _PreparedPage(terminal_record, normalized), was_created


def _existing_transcription_record(
    root: Path, relative: Path, *, page_id: str, pdf_page: int
) -> _PreparedPage | None:
    try:
        package = safe_path(root, relative.as_posix())
        package.lstat()
    except FileNotFoundError:
        return None
    except (OSError, StorageError) as exc:
        raise TranscriptionError(
            f"cannot inspect existing transcription package: {exc}"
        ) from exc
    evidence_payload, evidence_snapshot = read_attested_bytes(
        safe_path(package, "evidence.json")
    )
    evidence = loads_object(evidence_payload.decode("utf-8"), description="page evidence")
    source = cast(JsonObject, evidence["source"])
    probe = cast(JsonObject, evidence["probe"])
    artifacts = cast(list[JsonObject], evidence["artifacts"])
    by_role = {cast(str, artifact["role"]): artifact for artifact in artifacts}
    normalized_artifact = by_role["normalized_search_text"]
    model_artifact = by_role["model_input_render"]
    normalized_payload, _ = read_attested_bytes(
        safe_path(root, cast(str, normalized_artifact["path"])),
        expected_sha256=cast(str, normalized_artifact["sha256"]),
        expected_bytes=cast(int, normalized_artifact["bytes"]),
    )
    record: JsonObject = {
        "page_id": evidence["page_id"],
        "pdf_page": pdf_page,
        "state": evidence["state"],
        "classification": probe["classification"],
        "route": probe["route"],
        "reason_codes": evidence["reason_codes"],
        "printed_page_label": source["printed_page_label"],
        "package_path": relative.as_posix(),
        "package_sha256": evidence_snapshot.sha256,
        "normalized_sha256": normalized_artifact["sha256"],
        "normalized_chars": len(normalized_payload.decode("utf-8")),
        "model_input_bytes": cast(int, normalized_artifact["bytes"])
        + cast(int, model_artifact["bytes"]),
        "error": None,
    }
    if record["page_id"] != page_id:
        raise TranscriptionError("existing transcription package has a false page ID")
    _validate_transcription_package(record, root=root)
    return _PreparedPage(record, normalized_payload.decode("utf-8"))


def _failed_prepared(page: JsonObject, code: str, exc: Exception) -> _PreparedPage:
    return _PreparedPage(_failed_record(page, code, f"{type(exc).__name__}: {exc}"), "")


def _failed_record(page: JsonObject, code: str, diagnostic: str) -> JsonObject:
    return {
        "page_id": page["page_id"],
        "pdf_page": page["pdf_page"],
        "state": "failed",
        "classification": page["classification"],
        "route": page["route"],
        "reason_codes": [],
        "printed_page_label": None,
        "package_path": None,
        "package_sha256": None,
        "normalized_sha256": None,
        "normalized_chars": 0,
        "model_input_bytes": 0,
        "error": {"code": code, "diagnostic": diagnostic[:1000]},
    }


def _model_render(payload: bytes, *, max_edge: int, quality: int) -> bytes:
    try:
        with Image.open(BytesIO(payload)) as source:
            image = source.convert("RGB")
    except Exception as exc:
        raise TranscriptionError(
            f"source render cannot be decoded: {type(exc).__name__}"
        ) from exc
    scale = min(1.0, max_edge / max(image.width, image.height))
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    if size != image.size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=quality,
        optimize=False,
        progressive=False,
        subsampling=0,
    )
    return output.getvalue()


def _ocr_preprocessing(
    payload: bytes, *, catalog_key: str, classification: str
) -> tuple[bytes, list[str]]:
    try:
        with Image.open(BytesIO(payload)) as source:
            grayscale = source.convert("L")
    except Exception as exc:
        raise TranscriptionError(
            f"source render cannot be preprocessed: {type(exc).__name__}"
        ) from exc
    operations = ["grayscale"]
    if catalog_key == "volume-17-edition-1403":
        threshold = _otsu_threshold(grayscale.histogram())
        grayscale = grayscale.point(lambda value: 255 if value > threshold else 0)
        operations.append("otsu_global")
    elif classification not in {"image_scan", "degraded_photo"}:
        operations = ["grayscale"]
    output = BytesIO()
    grayscale.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue(), operations


def _otsu_threshold(histogram: list[int]) -> int:
    total = sum(histogram)
    weighted_total = sum(index * count for index, count in enumerate(histogram))
    background_weight = 0
    background_sum = 0
    best_variance = -1.0
    threshold = 127
    for index, count in enumerate(histogram):
        background_weight += count
        if background_weight == 0:
            continue
        foreground_weight = total - background_weight
        if foreground_weight == 0:
            break
        background_sum += index * count
        background_mean = background_sum / background_weight
        foreground_mean = (weighted_total - background_sum) / foreground_weight
        variance = (
            background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
        )
        if variance > best_variance:
            best_variance = variance
            threshold = index
    return threshold


def _ocr_attempt(output: OcrOutput, *, page_segmentation_mode: int) -> JsonObject:
    confidences = [cast(int, token["confidence_permyriad"]) for token in output.tokens]
    return {
        "page_segmentation_mode": page_segmentation_mode,
        "token_count": len(output.tokens),
        "line_count": len(output.lines),
        "mean_confidence_permyriad": (
            sum(confidences) // len(confidences) if confidences else 0
        ),
    }


def _ocr_score(output: OcrOutput) -> tuple[int, int]:
    confidences = [cast(int, token["confidence_permyriad"]) for token in output.tokens]
    mean = sum(confidences) // len(confidences) if confidences else 0
    return len(output.tokens), mean


def _needs_dense_fallback(output: OcrOutput) -> bool:
    token_count, mean = _ocr_score(output)
    return token_count < 20 or mean < 6000


def _critical_ocr_token(value: str) -> bool:
    return any(character.isdigit() for character in value) or bool(
        _EQUATION_MARKERS.search(value)
    )


def _symbol_candidates(
    native: JsonObject,
    ocr: JsonObject | None,
    render_payload: bytes,
    *,
    page_id: str,
) -> tuple[list[JsonObject], dict[str, bytes]]:
    sources: list[tuple[str, JsonObject]] = [
        ("native", line) for line in cast(list[JsonObject], native["lines"])
    ]
    if ocr is not None:
        sources.extend(("ocr", line) for line in cast(list[JsonObject], ocr["lines"]))
    candidates: list[JsonObject] = []
    crop_files: dict[str, bytes] = {}
    equation_index = 0
    for source_kind, line in sources:
        raw_text = cast(str, line["raw_text"])
        bbox = cast(list[int], line["bbox"])
        if _EQUATION_MARKERS.search(raw_text):
            candidate_id = f"{page_id}:equation:{equation_index:04d}"
            crop_name = f"formula-crops/{equation_index:04d}.png"
            crop_files[crop_name] = _crop_line(
                render_payload,
                bbox,
                source_kind=source_kind,
                native=native,
            )
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "kind": "equation",
                    "source_kind": source_kind,
                    "span_id": line["span_id"],
                    "raw_text": raw_text,
                    "bbox": bbox,
                    "crop_file": crop_name,
                }
            )
            equation_index += 1
        for match in _ABBREVIATION_PATTERN.finditer(raw_text):
            candidates.append(
                {
                    "candidate_id": f"{page_id}:abbreviation:{len(candidates):04d}",
                    "kind": "method_abbreviation",
                    "source_kind": source_kind,
                    "span_id": line["span_id"],
                    "raw_text": match.group(1),
                    "bbox": bbox,
                    "crop_file": None,
                }
            )
        for match in _UNIT_PATTERN.finditer(raw_text):
            candidates.append(
                {
                    "candidate_id": f"{page_id}:unit:{len(candidates):04d}",
                    "kind": "unit_mention",
                    "source_kind": source_kind,
                    "span_id": line["span_id"],
                    "raw_text": match.group(0),
                    "bbox": bbox,
                    "crop_file": None,
                }
            )
    return candidates, crop_files


def _crop_line(
    render_payload: bytes,
    bbox: list[int],
    *,
    source_kind: str,
    native: JsonObject,
) -> bytes:
    with Image.open(BytesIO(render_payload)) as source:
        image = source.convert("RGB")
    if source_kind == "native":
        coordinate = cast(JsonObject, native["coordinate_space"])
        width = cast(int, coordinate["width"])
        height = cast(int, coordinate["height"])
        left = bbox[0] * image.width // max(1, width)
        right = bbox[2] * image.width // max(1, width)
        top = image.height - bbox[3] * image.height // max(1, height)
        bottom = image.height - bbox[1] * image.height // max(1, height)
    else:
        left, top, right, bottom = bbox
    padding = 8
    crop = image.crop(
        (
            max(0, left - padding),
            max(0, top - padding),
            min(image.width, right + padding),
            min(image.height, bottom + padding),
        )
    )
    output = BytesIO()
    crop.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _printed_page_label(native: JsonObject, ocr: JsonObject | None) -> str | None:
    values = cast(list[str], native["raw_line_text"])
    if ocr is not None:
        values += [
            cast(str, line["raw_text"]) for line in cast(list[JsonObject], ocr["lines"])
        ]
    for value in [*values[:2], *values[-2:]]:
        candidate = value.strip()
        if candidate and _PRINTED_LABEL_PATTERN.fullmatch(candidate):
            return candidate
    return None


def _table_candidates(page: JsonObject, native: JsonObject) -> list[JsonObject]:
    metrics = cast(JsonObject, page["metrics"])
    numeric_lines = sum(
        sum(character.isdigit() for character in cast(str, line["raw_text"])) >= 3
        for line in cast(list[JsonObject], native["lines"])
    )
    reasons: list[str] = []
    if cast(int, metrics["shape_count"]) >= 8:
        reasons.append("MANY_VECTOR_SHAPES")
    if numeric_lines >= 4:
        reasons.append("MULTIPLE_NUMERIC_LINES")
    if not reasons:
        return []
    return [{"kind": "table_like_region", "reasons": reasons}]


def _artifact_record(relative: Path, name: str, payload: bytes) -> JsonObject:
    media_type = {
        ".json": "application/json",
        ".txt": "text/plain; charset=utf-8",
        ".jpg": "image/jpeg",
        ".png": "image/png",
    }[Path(name).suffix]
    return {
        "role": _artifact_role(name),
        "path": (relative / name).as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "media_type": media_type,
    }


def _artifact_role(name: str) -> str:
    if name.startswith("formula-crops/"):
        return "formula_crop"
    return {
        "raw-native.txt": "raw_native_text",
        "normalized.txt": "normalized_search_text",
        "digits-ascii.txt": "ascii_digit_view",
        "model.jpg": "model_input_render",
        "ocr.json": "ocr_layout",
        "ocr-input.png": "ocr_input_render",
    }[name]


def _install_package(
    root: Path, relative: Path, files: dict[str, bytes], required_file: str
) -> bool:
    try:
        ensure_private_tree(root, relative.parent.as_posix())
        destination = safe_path(root, relative.as_posix())
        temporary = make_temporary_directory(destination.parent, prefix=".transcribe.")
        try:
            for name, payload in files.items():
                parent = Path(name).parent
                if parent != Path():
                    ensure_private_tree(temporary, parent.as_posix())
                install_immutable_bytes(safe_path(temporary, name), payload)
            result = install_terminal_directory(
                temporary, destination, required_file=required_file
            )
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return result.status is InstallStatus.INSTALLED
    except StorageError as exc:
        raise TranscriptionError(str(exc)) from exc


def _build_bundles(
    document: JsonObject,
    *,
    root: Path,
    configuration: JsonObject,
    max_pages: int,
    max_bytes: int,
) -> tuple[list[JsonObject], int, int]:
    pages = cast(list[JsonObject], document["pages"])
    continuation_edges = _continuation_edges(pages, root=root)
    continued_to = {cast(int, edge["to_pdf_page"]) for edge in continuation_edges}
    chunks: list[list[JsonObject]] = []
    index = 0
    while index < len(pages):
        chunk: list[JsonObject] = []
        byte_size = 0
        if index > 0 and cast(int, pages[index]["pdf_page"]) in continued_to:
            previous = pages[index - 1]
            overlap_bytes = cast(int, previous["model_input_bytes"])
            next_bytes = cast(int, pages[index]["model_input_bytes"])
            if max_pages >= 2 and overlap_bytes + next_bytes <= max_bytes:
                chunk.append(previous)
                byte_size = overlap_bytes
        while index < len(pages) and len(chunk) < max_pages:
            candidate = pages[index]
            candidate_bytes = cast(int, candidate["model_input_bytes"])
            if chunk and byte_size + candidate_bytes > max_bytes:
                break
            chunk.append(candidate)
            byte_size += candidate_bytes
            index += 1
            if candidate_bytes > max_bytes:
                break
        if not chunk:
            chunk.append(pages[index])
            index += 1
        chunks.append(chunk)
    records: list[JsonObject] = []
    created = 0
    reused = 0
    source_sha256 = cast(str, document["source_sha256"])
    for sequence, chunk in enumerate(chunks, start=1):
        start = cast(int, chunk[0]["pdf_page"])
        end = cast(int, chunk[-1]["pdf_page"])
        page_refs = [_bundle_page_ref(page, root=root) for page in chunk]
        byte_size = sum(cast(int, ref["input_bytes"]) for ref in page_refs)
        bundle_id = (
            f"sha256:{source_sha256}:bundle:{start:06d}-{end:06d}:"
            f"{cast(str, configuration['sha256'])[:16]}"
        )
        edges = [
            edge
            for edge in continuation_edges
            if start <= cast(int, edge["from_pdf_page"]) <= end
            or start <= cast(int, edge["to_pdf_page"]) <= end
        ]
        bundle: JsonObject = {
            "schema_version": "1.0.0",
            "bundle_id": bundle_id,
            "catalog_key": document["catalog_key"],
            "source_sha256": source_sha256,
            "configuration_sha256": configuration["sha256"],
            "sequence": sequence,
            "start_pdf_page": start,
            "end_pdf_page": end,
            "page_count": len(chunk),
            "input_bytes": byte_size,
            "byte_ceiling": max_bytes,
            "pages": page_refs,
            "continuation_edges": edges,
            "fallback": "page_by_page" if len(chunk) == 1 else "bounded_bundle",
        }
        _validate_bundle(bundle)
        bundle_payload = canonical_bytes(bundle)
        bundle_sha256 = hashlib.sha256(bundle_payload).hexdigest()
        relative = (
            Path("bundles")
            / source_sha256
            / cast(str, configuration["sha256"])
            / f"{sequence:06d}-{start:06d}-{end:06d}-{bundle_sha256}.json"
        )
        try:
            ensure_private_tree(root, relative.parent.as_posix())
            status = install_immutable_bytes(
                safe_path(root, relative.as_posix()), bundle_payload
            ).status
        except StorageError as exc:
            raise TranscriptionError(str(exc)) from exc
        created += status is InstallStatus.INSTALLED
        reused += status is InstallStatus.REUSED
        records.append(
            {
                "bundle_id": bundle_id,
                "sequence": sequence,
                "start_pdf_page": start,
                "end_pdf_page": end,
                "page_count": len(chunk),
                "input_bytes": byte_size,
                "path": relative.as_posix(),
                "sha256": bundle_sha256,
            }
        )
    return records, created, reused


def _bundle_page_ref(page: JsonObject, *, root: Path) -> JsonObject:
    if page["package_path"] is None:
        return {
            "page_id": page["page_id"],
            "pdf_page": page["pdf_page"],
            "state": page["state"],
            "span_ids": [],
            "raw_native_text_path": None,
            "normalized_text_path": None,
            "model_render_path": None,
            "input_bytes": 0,
        }
    package = Path(cast(str, page["package_path"]))
    raw_native = (package / "raw-native.txt").as_posix()
    normalized = (package / "normalized.txt").as_posix()
    model = (package / "model.jpg").as_posix()
    evidence_payload, _ = read_attested_bytes(
        safe_path(root, (package / "evidence.json").as_posix())
    )
    evidence = loads_object(evidence_payload.decode("utf-8"), description="page evidence")
    probe_package = Path(cast(str, cast(JsonObject, evidence["probe"])["package_path"]))
    native_payload, _ = read_attested_bytes(
        safe_path(root, (probe_package / "native.json").as_posix())
    )
    native = loads_object(native_payload.decode("utf-8"), description="native layout")
    span_ids = [
        cast(str, line["span_id"]) for line in cast(list[JsonObject], native["lines"])
    ]
    route = cast(str, cast(JsonObject, evidence["probe"])["route"])
    if route in {"ocr", "native_plus_ocr"}:
        ocr_path = package / "ocr.json"
        ocr_payload, _ = read_attested_bytes(safe_path(root, ocr_path.as_posix()))
        ocr = loads_object(ocr_payload.decode("utf-8"), description="OCR layout")
        span_ids.extend(
            cast(str, line["span_id"]) for line in cast(list[JsonObject], ocr["lines"])
        )
    read_attested_bytes(safe_path(root, raw_native))
    read_attested_bytes(safe_path(root, normalized))
    read_attested_bytes(safe_path(root, model))
    return {
        "page_id": page["page_id"],
        "pdf_page": page["pdf_page"],
        "state": page["state"],
        "span_ids": span_ids,
        "raw_native_text_path": raw_native,
        "normalized_text_path": normalized,
        "model_render_path": model,
        "input_bytes": page["model_input_bytes"],
    }


def _continuation_edges(pages: list[JsonObject], *, root: Path) -> list[JsonObject]:
    edges: list[JsonObject] = []
    for left, right in pairwise(pages):
        if left["package_path"] is None or right["package_path"] is None:
            continue
        left_text = _normalized_text(left, root=root).rstrip()
        right_text = _normalized_text(right, root=root).lstrip()
        if (
            left_text
            and right_text
            and left_text[-1] not in _SENTENCE_ENDINGS
            and cast(int, right["pdf_page"]) == cast(int, left["pdf_page"]) + 1
        ):
            edges.append(
                {
                    "from_page_id": left["page_id"],
                    "to_page_id": right["page_id"],
                    "from_pdf_page": left["pdf_page"],
                    "to_pdf_page": right["pdf_page"],
                    "reason": "PREVIOUS_PAGE_LACKS_TERMINAL_PUNCTUATION",
                }
            )
    return edges


def _normalized_text(page: JsonObject, *, root: Path) -> str:
    package = Path(cast(str, page["package_path"]))
    payload, _ = read_attested_bytes(
        safe_path(root, (package / "normalized.txt").as_posix())
    )
    return payload.decode("utf-8")


def _summarize(
    pages: list[JsonObject], bundles: list[JsonObject], documents: list[JsonObject]
) -> JsonObject:
    return {
        "documents_expected": len(documents),
        "documents_processed": len(documents),
        "pages_expected": len(pages),
        "pages_ready": sum(page["state"] == "ready" for page in pages),
        "pages_needs_review": sum(page["state"] == "needs_review" for page in pages),
        "pages_failed": sum(page["state"] == "failed" for page in pages),
        "ocr_pages": sum(page["route"] in {"ocr", "native_plus_ocr"} for page in pages),
        "bundles": len(bundles),
    }


def validate_transcription(
    manifest: JsonObject, *, root: Path | None = None, probe: JsonObject | None = None
) -> None:
    """Reject structurally or semantically false transcription output."""
    try:
        schema = load_packaged_json(
            "cadgpt_regulations.schemas", "transcription.schema.json"
        )
        validate_schema(manifest, schema, description="transcription")
    except ManifestError as exc:
        raise TranscriptionError(str(exc)) from exc
    configuration = cast(JsonObject, manifest["configuration"])
    values = dict(configuration)
    digest = cast(str, values.pop("sha256"))
    if sha256_json(values) != digest:
        raise TranscriptionError("transcription configuration SHA-256 is false")
    documents = cast(list[JsonObject], manifest["documents"])
    pages = [
        page for document in documents for page in cast(list[JsonObject], document["pages"])
    ]
    bundles = [
        bundle
        for document in documents
        for bundle in cast(list[JsonObject], document["bundles"])
    ]
    if manifest["summary"] != _summarize(pages, bundles, documents):
        raise TranscriptionError("transcription summary differs from its records")
    if probe is not None:
        if (
            manifest["catalog"] != probe["catalog"]
            or manifest["acquisition"] != probe["acquisition"]
        ):
            raise TranscriptionError(
                "transcription source identity differs from page probe"
            )
        if (
            cast(JsonObject, manifest["probe"])["sha256"]
            != hashlib.sha256(canonical_bytes(probe)).hexdigest()
        ):
            raise TranscriptionError("transcription page-probe digest is false")
        probe_documents = cast(list[JsonObject], probe["documents"])
        if len(documents) != len(probe_documents):
            raise TranscriptionError("transcription document coverage differs from probe")
        for document, probe_document in zip(documents, probe_documents, strict=True):
            expected = [
                (page["page_id"], page["pdf_page"])
                for page in cast(list[JsonObject], probe_document["pages"])
            ]
            actual = [
                (page["page_id"], page["pdf_page"])
                for page in cast(list[JsonObject], document["pages"])
            ]
            if actual != expected:
                raise TranscriptionError("transcription page coverage differs from probe")
            _validate_document_bundles(document)
    if root is not None:
        for page in pages:
            if page["package_path"] is not None:
                _validate_transcription_package(page, root=root)
        for bundle in bundles:
            path = safe_path(root, cast(str, bundle["path"]))
            payload, _ = read_attested_bytes(
                path, expected_sha256=cast(str, bundle["sha256"])
            )
            bundle_record = loads_object(payload.decode("utf-8"), description="bundle")
            _validate_bundle(bundle_record)


def _validate_transcription_package(page: JsonObject, *, root: Path) -> None:
    try:
        package = safe_path(root, cast(str, page["package_path"]))
        snapshot_directory(package)
        payload, _ = read_attested_bytes(
            safe_path(package, "evidence.json"),
            expected_sha256=cast(str, page["package_sha256"]),
        )
        evidence = loads_object(payload.decode("utf-8"), description="page evidence")
        schema = load_packaged_json(
            "cadgpt_regulations.schemas", "page-evidence.schema.json"
        )
        validate_schema(evidence, schema, description="page evidence")
        if evidence["page_id"] != page["page_id"] or evidence["state"] != page["state"]:
            raise TranscriptionError("stored page evidence differs from manifest")
        artifacts = cast(list[JsonObject], evidence["artifacts"])
        artifact_paths = [cast(str, artifact["path"]) for artifact in artifacts]
        if len(set(artifact_paths)) != len(artifact_paths):
            raise TranscriptionError("page evidence artifact paths are duplicated")
        roles = [cast(str, artifact["role"]) for artifact in artifacts]
        for required_role in (
            "raw_native_text",
            "normalized_search_text",
            "ascii_digit_view",
            "model_input_render",
        ):
            if roles.count(required_role) != 1:
                raise TranscriptionError(
                    f"page evidence requires exactly one {required_role} artifact"
                )
        route = cast(str, cast(JsonObject, evidence["probe"])["route"])
        expected_ocr = route in {"ocr", "native_plus_ocr"}
        if roles.count("ocr_layout") != int(expected_ocr) or roles.count(
            "ocr_input_render"
        ) != int(expected_ocr):
            raise TranscriptionError("page evidence OCR artifacts differ from its route")
        paths: set[str] = {"evidence.json"}
        for artifact in artifacts:
            path = safe_path(root, cast(str, artifact["path"]))
            try:
                path.relative_to(package)
            except ValueError as exc:
                raise TranscriptionError(
                    "page evidence artifact escapes its package"
                ) from exc
            read_attested_bytes(
                path,
                expected_sha256=cast(str, artifact["sha256"]),
                expected_bytes=cast(int, artifact["bytes"]),
            )
            paths.add(path.relative_to(package).as_posix())
            if artifact["role"] == "ocr_layout":
                ocr_payload, _ = read_attested_bytes(
                    path,
                    expected_sha256=cast(str, artifact["sha256"]),
                    expected_bytes=cast(int, artifact["bytes"]),
                )
                ocr = loads_object(ocr_payload.decode("utf-8"), description="OCR layout")
                _validate_ocr(ocr, page_id=cast(str, page["page_id"]))
            if (
                artifact["role"] == "normalized_search_text"
                and artifact["sha256"] != page["normalized_sha256"]
            ):
                raise TranscriptionError("normalized text digest differs from manifest")
        actual = {
            entry.path
            for entry in snapshot_directory(package).entries
            if entry.kind == "file"
        }
        if actual != paths:
            raise TranscriptionError("page evidence package has unindexed files")
    except (ManifestError, StorageError) as exc:
        raise TranscriptionError(str(exc)) from exc


def _validate_document_bundles(document: JsonObject) -> None:
    pages = cast(list[JsonObject], document["pages"])
    bundles = cast(list[JsonObject], document["bundles"])
    if [bundle["sequence"] for bundle in bundles] != list(range(1, len(bundles) + 1)):
        raise TranscriptionError("bundle sequences are missing or reordered")
    page_numbers = [cast(int, page["pdf_page"]) for page in pages]
    covered: set[int] = set()
    previous_end: int | None = None
    for bundle in bundles:
        start = cast(int, bundle["start_pdf_page"])
        end = cast(int, bundle["end_pdf_page"])
        if previous_end is not None and start not in {previous_end, previous_end + 1}:
            raise TranscriptionError("bundle ranges have a gap or excessive overlap")
        covered.update(range(start, end + 1))
        previous_end = end
    if covered != set(page_numbers):
        raise TranscriptionError("bundles do not cover every document page")


def _validate_ocr(ocr: JsonObject, *, page_id: str) -> None:
    try:
        schema = load_packaged_json("cadgpt_regulations.schemas", "ocr-layout.schema.json")
        validate_schema(ocr, schema, description="OCR layout")
    except ManifestError as exc:
        raise TranscriptionError(str(exc)) from exc
    if ocr["page_id"] != page_id:
        raise TranscriptionError("OCR layout has a false page ID")
    tokens = cast(list[JsonObject], ocr["tokens"])
    lines = cast(list[JsonObject], ocr["lines"])
    if [token["span_id"] for token in tokens] != [
        f"{page_id}:ocr:word:{index:06d}" for index in range(len(tokens))
    ]:
        raise TranscriptionError("OCR token span IDs are false or reordered")
    if [line["span_id"] for line in lines] != [
        f"{page_id}:ocr:line:{index:06d}" for index in range(len(lines))
    ]:
        raise TranscriptionError("OCR line span IDs are false or reordered")


def _validate_bundle(bundle: JsonObject) -> None:
    try:
        schema = load_packaged_json("cadgpt_regulations.schemas", "bundle.schema.json")
        validate_schema(bundle, schema, description="model bundle")
    except ManifestError as exc:
        raise TranscriptionError(str(exc)) from exc
    pages = cast(list[JsonObject], bundle["pages"])
    numbers = [cast(int, page["pdf_page"]) for page in pages]
    if numbers != list(range(numbers[0], numbers[-1] + 1)):
        raise TranscriptionError("bundle pages are not ordered and contiguous")
    if len(pages) > 10:
        raise TranscriptionError("bundle exceeds ten pages")
    if (
        bundle["page_count"] != len(pages)
        or bundle["start_pdf_page"] != numbers[0]
        or bundle["end_pdf_page"] != numbers[-1]
    ):
        raise TranscriptionError("bundle range/count differs from its pages")
    total = sum(cast(int, page["input_bytes"]) for page in pages)
    if total != bundle["input_bytes"]:
        raise TranscriptionError("bundle byte total is false")
    if total > cast(int, bundle["byte_ceiling"]) and len(pages) != 1:
        raise TranscriptionError("multi-page bundle exceeds its byte ceiling")


def _install_manifest(root: Path, manifest: JsonObject) -> tuple[Path, bool]:
    payload = canonical_bytes(manifest)
    digest = hashlib.sha256(payload).hexdigest()
    relative = Path("manifests") / "transcription" / f"{digest}.json"
    index_relative = Path("indexes") / "transcription" / f"{digest}.json"
    index: JsonObject = {
        "schema_version": "1.0.0",
        "kind": "transcription",
        "manifest_path": relative.as_posix(),
        "manifest_sha256": digest,
        "configuration_sha256": cast(JsonObject, manifest["configuration"])["sha256"],
        "probe_sha256": cast(JsonObject, manifest["probe"])["sha256"],
    }
    try:
        ensure_private_tree(root, relative.parent.as_posix())
        ensure_private_tree(root, index_relative.parent.as_posix())
        result = install_immutable_bytes(safe_path(root, relative.as_posix()), payload)
        install_immutable_bytes(
            safe_path(root, index_relative.as_posix()), canonical_bytes(index)
        )
    except StorageError as exc:
        raise TranscriptionError(str(exc)) from exc
    return safe_path(root, relative.as_posix()), result.status is InstallStatus.INSTALLED
