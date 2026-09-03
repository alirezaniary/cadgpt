"""Deterministic page probing and immutable source-evidence packaging."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from cadgpt_regulations.acquisition import validate_acquisition_receipt
from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.errors import ManifestError, TranscriptionError
from cadgpt_regulations.jsonio import (
    JsonObject,
    canonical_bytes,
    load_object,
    loads_object,
    sha256_json,
    validate_schema,
)
from cadgpt_regulations.page_tools import run_probe_worker, runtime_toolchain
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.storage import (
    InstallStatus,
    StorageError,
    ensure_private_tree,
    install_immutable_bytes,
    install_terminal_directory,
    make_temporary_directory,
    read_attested_bytes,
    read_regular_snapshot,
    safe_path,
    snapshot_directory,
    stage_attested_copy,
    validate_output_root,
)
from cadgpt_regulations.store_index import validate_output_inventory

PAGE_PROBE_SCHEMA_VERSION = "1.0.0"
DEFAULT_RENDER_DPI = 400
DEFAULT_PAGE_TIMEOUT_SECONDS = 180

_CLASSIFICATIONS = (
    "blank",
    "native_text",
    "suspect_native",
    "image_scan",
    "mixed",
    "degraded_photo",
)
_ROUTES = ("none", "native", "ocr", "native_plus_ocr")
_MIN_NATIVE_NONSPACE_CHARS = 20
_MIXED_BITMAP_COVERAGE_PERMYRIAD = 1_000
_SCAN_BITMAP_COVERAGE_PERMYRIAD = 8_000
_BLANK_INK_COVERAGE_PERMYRIAD = 30


@dataclass(frozen=True)
class ProbeRun:
    """Canonical result plus operational reuse facts excluded from its identity."""

    manifest: JsonObject
    packages_created: int
    packages_reused: int
    manifest_created: bool
    manifest_path: Path


def parse_page_range(value: str) -> tuple[int, int]:
    """Parse one inclusive CLI page range such as ``11-20`` or ``4``."""
    start_text, separator, end_text = value.partition("-")
    try:
        start = int(start_text)
        end = int(end_text) if separator else start
    except ValueError as exc:
        raise TranscriptionError(f"invalid page range: {value!r}") from exc
    if start < 1 or end < start:
        raise TranscriptionError(f"invalid page range: {value!r}")
    return start, end


def build_page_probe(
    acquisition: JsonObject,
    *,
    acquisition_root: Path,
    output_root: Path,
    catalog: JsonObject | None = None,
    catalog_keys: tuple[str, ...] = (),
    page_ranges: tuple[tuple[int, int], ...] = (),
    render_dpi: int = DEFAULT_RENDER_DPI,
    tessdata_directory: Path | None = None,
    workers: int = 1,
    page_timeout_seconds: int = DEFAULT_PAGE_TIMEOUT_SECONDS,
) -> ProbeRun:
    """Re-attest source PDFs and build terminal packages for every selected page."""
    curated = load_catalog() if catalog is None else catalog
    validate_acquisition_receipt(acquisition, catalog=curated, root=acquisition_root)
    try:
        validate_output_root(output_root)
    except StorageError as exc:
        raise TranscriptionError(str(exc)) from exc
    if render_dpi < 72 or render_dpi > 600:
        raise TranscriptionError("render DPI must be between 72 and 600")
    if workers < 1:
        raise TranscriptionError("page-probe workers must be at least one")
    if page_timeout_seconds < 1 or page_timeout_seconds > 3_600:
        raise TranscriptionError("page timeout must be between 1 and 3600 seconds")

    artifacts = cast(list[JsonObject], acquisition["artifacts"])
    selected = _select_artifacts(artifacts, catalog_keys)
    normalized_ranges = _normalize_ranges(page_ranges)
    configuration_values: JsonObject = {
        "schema_version": "1.0.0",
        "render_dpi": render_dpi,
        "page_timeout_seconds": page_timeout_seconds,
        "parser_boundary": "crop_box",
        "thresholds": {
            "minimum_native_nonspace_chars": _MIN_NATIVE_NONSPACE_CHARS,
            "mixed_bitmap_coverage_permyriad": _MIXED_BITMAP_COVERAGE_PERMYRIAD,
            "scan_bitmap_coverage_permyriad": _SCAN_BITMAP_COVERAGE_PERMYRIAD,
            "blank_ink_coverage_permyriad": _BLANK_INK_COVERAGE_PERMYRIAD,
        },
    }
    configuration = {**configuration_values, "sha256": sha256_json(configuration_values)}
    toolchain = runtime_toolchain(tessdata_directory)
    toolchain_sha256 = sha256_json(toolchain)

    documents: list[JsonObject] = []
    packages_created = 0
    packages_reused = 0
    for artifact in selected:
        document, created, reused = _probe_document(
            artifact,
            acquisition_root=acquisition_root,
            output_root=output_root,
            page_ranges=normalized_ranges,
            configuration=configuration,
            toolchain=toolchain,
            toolchain_sha256=toolchain_sha256,
            render_dpi=render_dpi,
            workers=workers,
            page_timeout_seconds=page_timeout_seconds,
        )
        documents.append(document)
        packages_created += created
        packages_reused += reused

    page_records = [
        page for document in documents for page in cast(list[JsonObject], document["pages"])
    ]
    summary = _summarize(documents, page_records)
    manifest: JsonObject = {
        "schema_version": PAGE_PROBE_SCHEMA_VERSION,
        "catalog": cast(JsonObject, acquisition["catalog"]),
        "acquisition": {"receipt_sha256": sha256_json(acquisition)},
        "configuration": configuration,
        "toolchain": toolchain,
        "toolchain_sha256": toolchain_sha256,
        "selection": {
            "catalog_keys": list(catalog_keys) if catalog_keys else None,
            "page_ranges": [
                {"start": start, "end": end} for start, end in normalized_ranges
            ],
        },
        "documents": documents,
        "summary": summary,
    }
    validate_page_probe(manifest, root=output_root, acquisition=acquisition)
    manifest_path, manifest_created = _install_manifest(output_root, manifest)
    validate_output_inventory(output_root)
    validate_acquisition_receipt(acquisition, catalog=curated, root=acquisition_root)
    return ProbeRun(
        manifest=manifest,
        packages_created=packages_created,
        packages_reused=packages_reused,
        manifest_created=manifest_created,
        manifest_path=manifest_path,
    )


def _probe_document(
    artifact: JsonObject,
    *,
    acquisition_root: Path,
    output_root: Path,
    page_ranges: tuple[tuple[int, int], ...],
    configuration: JsonObject,
    toolchain: JsonObject,
    toolchain_sha256: str,
    render_dpi: int,
    workers: int,
    page_timeout_seconds: int,
) -> tuple[JsonObject, int, int]:
    page_count = cast(int, artifact["pdf_page_count"])
    pages = _selected_pages(page_count, page_ranges)
    document: JsonObject = {
        "catalog_key": artifact["catalog_key"],
        "catalog_order": artifact["catalog_order"],
        "source_sha256": artifact["sha256"],
        "source_bytes": artifact["bytes"],
        "pdf_page_count": page_count,
        "artifact_path": artifact["artifact_path"],
        "pages": [],
    }
    if artifact["state"] != "ready" or artifact["artifact_path"] is None:
        error = cast(JsonObject, artifact["error"])
        document["pages"] = [
            _failed_page(
                cast(str, artifact["sha256"] or artifact["expected_sha256"]),
                page_number,
                "SOURCE_NOT_READY",
                cast(str, error["diagnostic"]),
            )
            for page_number in pages
        ]
        return document, 0, 0

    try:
        source_path = safe_path(acquisition_root, cast(str, artifact["artifact_path"]))
    except StorageError as exc:
        document["pages"] = [
            _failed_page(
                cast(str, artifact["sha256"]),
                page_number,
                "SOURCE_PATH_UNSAFE",
                str(exc),
            )
            for page_number in pages
        ]
        return document, 0, 0
    created = 0
    reused = 0
    working_root: Path | None = None
    try:
        working_root = Path(tempfile.mkdtemp(prefix="cadgpt-page-probe-"))
        working_root.chmod(0o700)
        staged_source = working_root / "source.pdf"
        stage_attested_copy(
            source_path,
            staged_source,
            expected_sha256=cast(str, artifact["sha256"]),
            expected_bytes=cast(int, artifact["bytes"]),
        )
    except (OSError, StorageError) as exc:
        if working_root is not None:
            shutil.rmtree(working_root, ignore_errors=True)
        document["pages"] = [
            _failed_page(
                cast(str, artifact["sha256"]),
                page_number,
                "SOURCE_REATTESTATION_FAILED",
                str(exc),
            )
            for page_number in pages
        ]
        return document, 0, 0

    records_by_page: dict[int, JsonObject] = {}
    futures: dict[int, Future[tuple[JsonObject, bool]]] = {}
    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for page_number in pages:
                try:
                    futures[page_number] = executor.submit(
                        _probe_page,
                        staged_source,
                        artifact=artifact,
                        page_number=page_number,
                        output_root=output_root,
                        working_root=working_root,
                        configuration=configuration,
                        toolchain=toolchain,
                        toolchain_sha256=toolchain_sha256,
                        render_dpi=render_dpi,
                        page_timeout_seconds=page_timeout_seconds,
                    )
                except Exception as exc:  # noqa: BLE001 - page must be terminal
                    records_by_page[page_number] = _failed_page(
                        cast(str, artifact["sha256"]),
                        page_number,
                        "PAGE_SUBMIT_FAILED",
                        f"{type(exc).__name__}: {exc}",
                    )
            for page_number in pages:
                if page_number in records_by_page:
                    continue
                try:
                    record, was_created = futures[page_number].result()
                except Exception as exc:  # noqa: BLE001 - page must be terminal
                    record = _failed_page(
                        cast(str, artifact["sha256"]),
                        page_number,
                        "PAGE_PROBE_FAILED",
                        f"{type(exc).__name__}: {exc}",
                    )
                else:
                    if was_created:
                        created += 1
                    else:
                        reused += 1
                records_by_page[page_number] = record
    except Exception as exc:  # noqa: BLE001 - executor failure must not abort corpus
        for future in futures.values():
            future.cancel()
        for page_number in pages:
            records_by_page.setdefault(
                page_number,
                _failed_page(
                    cast(str, artifact["sha256"]),
                    page_number,
                    "PAGE_EXECUTOR_FAILED",
                    f"{type(exc).__name__}: {exc}",
                ),
            )
    finally:
        shutil.rmtree(working_root, ignore_errors=True)
    document["pages"] = [records_by_page[page_number] for page_number in pages]
    return document, created, reused


def _probe_page(
    source: Path,
    *,
    artifact: JsonObject,
    page_number: int,
    output_root: Path,
    working_root: Path,
    configuration: JsonObject,
    toolchain: JsonObject,
    toolchain_sha256: str,
    render_dpi: int,
    page_timeout_seconds: int,
) -> tuple[JsonObject, bool]:
    source_sha256 = cast(str, artifact["sha256"])
    page_id = _page_id(source_sha256, page_number)
    package_relative = (
        Path("pages")
        / source_sha256
        / cast(str, configuration["sha256"])
        / toolchain_sha256
        / f"{page_number:06d}"
    )
    existing = _existing_probe_record(
        output_root,
        package_relative,
        artifact=artifact,
        page_id=page_id,
        page_number=page_number,
        configuration_sha256=cast(str, configuration["sha256"]),
        toolchain=toolchain,
        toolchain_sha256=toolchain_sha256,
    )
    if existing is not None:
        return existing, False
    worker_directory = Path(
        tempfile.mkdtemp(prefix=f"page-{page_number:06d}-", dir=working_root)
    )
    worker_directory.chmod(0o700)
    try:
        worker = run_probe_worker(
            source,
            page_number=page_number,
            page_id=page_id,
            dpi=render_dpi,
            output_directory=worker_directory,
            timeout_seconds=page_timeout_seconds,
        )
        native = worker.native
        render = worker.render
        render_metrics = worker.render_metrics
    finally:
        try:
            shutil.rmtree(worker_directory)
        except OSError as exc:
            raise TranscriptionError(
                f"cannot clean page worker directory: {type(exc).__name__}"
            ) from exc
    _validate_native(native, page_id=page_id)
    metrics = _metrics(native, render_metrics)
    classification, route, state, reason_codes = _classify(metrics)

    native_relative = package_relative / "native.json"
    render_relative = package_relative / "render.png"
    native_bytes = canonical_bytes(native)
    native_digest = hashlib.sha256(native_bytes).hexdigest()
    render_digest = hashlib.sha256(render).hexdigest()
    page_package: JsonObject = {
        "schema_version": "1.0.0",
        "page_id": page_id,
        "source": {
            "catalog_key": artifact["catalog_key"],
            "catalog_order": artifact["catalog_order"],
            "sha256": source_sha256,
            "bytes": artifact["bytes"],
            "pdf_page_count": artifact["pdf_page_count"],
            "pdf_page": page_number,
        },
        "configuration_sha256": configuration["sha256"],
        "toolchain": toolchain,
        "toolchain_sha256": toolchain_sha256,
        "state": state,
        "classification": classification,
        "route": route,
        "reason_codes": reason_codes,
        "metrics": metrics,
        "artifacts": [
            {
                "role": "native_layout",
                "path": native_relative.as_posix(),
                "sha256": native_digest,
                "bytes": len(native_bytes),
                "media_type": "application/json",
            },
            {
                "role": "source_render",
                "path": render_relative.as_posix(),
                "sha256": render_digest,
                "bytes": len(render),
                "media_type": "image/png",
            },
        ],
        "error": None,
    }
    page_bytes = canonical_bytes(page_package)
    package_files = {
        "native.json": native_bytes,
        "render.png": render,
        "page.json": page_bytes,
    }
    was_created = _install_package(output_root, package_relative, package_files)
    return {
        "page_id": page_id,
        "pdf_page": page_number,
        "state": state,
        "classification": classification,
        "route": route,
        "reason_codes": reason_codes,
        "metrics": metrics,
        "package_path": package_relative.as_posix(),
        "package_sha256": hashlib.sha256(page_bytes).hexdigest(),
        "error": None,
    }, was_created


def _existing_probe_record(
    root: Path,
    relative: Path,
    *,
    artifact: JsonObject,
    page_id: str,
    page_number: int,
    configuration_sha256: str,
    toolchain: JsonObject,
    toolchain_sha256: str,
) -> JsonObject | None:
    try:
        package = safe_path(root, relative.as_posix())
        package.lstat()
    except FileNotFoundError:
        return None
    except (OSError, StorageError) as exc:
        raise TranscriptionError(f"cannot inspect existing page package: {exc}") from exc
    try:
        page_payload, page_snapshot = read_attested_bytes(safe_path(package, "page.json"))
        package_record = loads_object(
            page_payload.decode("utf-8"), description="page package"
        )
        page_record: JsonObject = {
            "page_id": package_record["page_id"],
            "pdf_page": page_number,
            "state": package_record["state"],
            "classification": package_record["classification"],
            "route": package_record["route"],
            "reason_codes": package_record["reason_codes"],
            "metrics": package_record["metrics"],
            "package_path": relative.as_posix(),
            "package_sha256": page_snapshot.sha256,
            "error": None,
        }
        document: JsonObject = {
            "catalog_key": artifact["catalog_key"],
            "catalog_order": artifact["catalog_order"],
            "source_sha256": artifact["sha256"],
            "source_bytes": artifact["bytes"],
            "pdf_page_count": artifact["pdf_page_count"],
        }
        if page_record["page_id"] != page_id:
            raise TranscriptionError("existing page package has a false page ID")
        _validate_stored_package(
            root,
            page_record,
            document=document,
            configuration_sha256=configuration_sha256,
            toolchain=toolchain,
            toolchain_sha256=toolchain_sha256,
        )
        return page_record
    except (ManifestError, StorageError, UnicodeError) as exc:
        raise TranscriptionError(str(exc)) from exc


def _metrics(native: JsonObject, render: JsonObject) -> JsonObject:
    raw_text = cast(str, native["raw_glyph_text"])
    resources = cast(JsonObject, native["resource_counts"])
    return {
        "native_char_cells": len(cast(list[JsonObject], native["chars"])),
        "native_nonspace_chars": sum(not character.isspace() for character in raw_text),
        "native_word_cells": len(cast(list[JsonObject], native["words"])),
        "native_line_cells": len(cast(list[JsonObject], native["lines"])),
        "bitmap_count": resources["bitmaps"],
        "shape_count": resources["shapes"],
        "bitmap_coverage_permyriad": native["bitmap_coverage_permyriad"],
        "ink_coverage_permyriad": render["ink_coverage_permyriad"],
        "render_width_pixels": render["width_pixels"],
        "render_height_pixels": render["height_pixels"],
    }


def _classify(metrics: JsonObject) -> tuple[str, str, str, list[str]]:
    chars = cast(int, metrics["native_nonspace_chars"])
    bitmap = cast(int, metrics["bitmap_coverage_permyriad"])
    ink = cast(int, metrics["ink_coverage_permyriad"])
    if chars == 0 and bitmap >= _SCAN_BITMAP_COVERAGE_PERMYRIAD:
        return "image_scan", "ocr", "ready", ["FULL_PAGE_BITMAP_WITHOUT_NATIVE_TEXT"]
    if chars == 0 and ink <= _BLANK_INK_COVERAGE_PERMYRIAD:
        return "blank", "none", "ready", ["NO_NATIVE_TEXT_AND_LOW_INK"]
    if chars == 0:
        return (
            "degraded_photo",
            "ocr",
            "needs_review",
            ["VISIBLE_CONTENT_WITHOUT_NATIVE_TEXT"],
        )
    if chars < _MIN_NATIVE_NONSPACE_CHARS:
        return (
            "suspect_native",
            "native_plus_ocr",
            "needs_review",
            ["LOW_NATIVE_TEXT_COUNT"],
        )
    if bitmap >= _MIXED_BITMAP_COVERAGE_PERMYRIAD:
        return "mixed", "native_plus_ocr", "ready", ["NATIVE_TEXT_AND_LARGE_BITMAP"]
    return "native_text", "native", "ready", ["SUFFICIENT_NATIVE_TEXT"]


def _failed_page(
    source_sha256: str, page_number: int, code: str, diagnostic: str
) -> JsonObject:
    return {
        "page_id": _page_id(source_sha256, page_number),
        "pdf_page": page_number,
        "state": "failed",
        "classification": None,
        "route": None,
        "reason_codes": [],
        "metrics": None,
        "package_path": None,
        "package_sha256": None,
        "error": {"code": code, "diagnostic": diagnostic},
    }


def _summarize(documents: list[JsonObject], pages: list[JsonObject]) -> JsonObject:
    classifications = {name: 0 for name in _CLASSIFICATIONS}
    routes = {name: 0 for name in _ROUTES}
    for page in pages:
        classification = page["classification"]
        route = page["route"]
        if classification is not None:
            classifications[cast(str, classification)] += 1
        if route is not None:
            routes[cast(str, route)] += 1
    return {
        "documents_expected": len(documents),
        "documents_processed": len(documents),
        "pages_expected": len(pages),
        "pages_ready": sum(page["state"] == "ready" for page in pages),
        "pages_needs_review": sum(page["state"] == "needs_review" for page in pages),
        "pages_failed": sum(page["state"] == "failed" for page in pages),
        "classifications": classifications,
        "routes": routes,
    }


def _select_artifacts(
    artifacts: list[JsonObject], catalog_keys: tuple[str, ...]
) -> list[JsonObject]:
    if len(set(catalog_keys)) != len(catalog_keys):
        raise TranscriptionError("catalog-key selectors must be unique")
    if not catalog_keys:
        return artifacts
    by_key = {cast(str, artifact["catalog_key"]): artifact for artifact in artifacts}
    unknown = [key for key in catalog_keys if key not in by_key]
    if unknown:
        raise TranscriptionError(f"unknown catalog key selector: {unknown[0]}")
    selected = set(catalog_keys)
    return [
        artifact for artifact in artifacts if cast(str, artifact["catalog_key"]) in selected
    ]


def _normalize_ranges(
    ranges: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    ordered = tuple(sorted(ranges))
    previous_end = 0
    for start, end in ordered:
        if start < 1 or end < start or start <= previous_end:
            raise TranscriptionError("page ranges must be positive, disjoint, and ordered")
        previous_end = end
    return ordered


def _selected_pages(
    page_count: int, ranges: tuple[tuple[int, int], ...]
) -> tuple[int, ...]:
    if not ranges:
        return tuple(range(1, page_count + 1))
    if ranges[-1][1] > page_count:
        raise TranscriptionError(
            f"selected page {ranges[-1][1]} exceeds document page count {page_count}"
        )
    return tuple(page for start, end in ranges for page in range(start, end + 1))


def _page_id(source_sha256: str, page_number: int) -> str:
    return f"sha256:{source_sha256}:page:{page_number:06d}"


def validate_page_probe(
    manifest: JsonObject,
    *,
    root: Path | None = None,
    acquisition: JsonObject | None = None,
) -> None:
    """Validate schema, semantic page accounting, and optional stored evidence."""
    _validate_manifest(manifest, root=root)
    if acquisition is not None:
        if manifest["catalog"] != acquisition["catalog"] or cast(
            JsonObject, manifest["acquisition"]
        )["receipt_sha256"] != sha256_json(acquisition):
            raise TranscriptionError(
                "page probe is not bound to the supplied acquisition receipt"
            )
        artifacts = cast(list[JsonObject], acquisition["artifacts"])
        selection = cast(JsonObject, manifest["selection"])
        selected_keys = cast(list[str] | None, selection["catalog_keys"])
        selected = (
            artifacts
            if selected_keys is None
            else [
                artifact
                for artifact in artifacts
                if artifact["catalog_key"] in set(selected_keys)
            ]
        )
        documents = cast(list[JsonObject], manifest["documents"])
        expected_documents = [
            (
                artifact["catalog_key"],
                artifact["catalog_order"],
                artifact["sha256"],
                artifact["bytes"],
                artifact["pdf_page_count"],
                artifact["artifact_path"],
            )
            for artifact in selected
        ]
        actual_documents = [
            (
                document["catalog_key"],
                document["catalog_order"],
                document["source_sha256"],
                document["source_bytes"],
                document["pdf_page_count"],
                document["artifact_path"],
            )
            for document in documents
        ]
        if actual_documents != expected_documents:
            raise TranscriptionError(
                "page probe document coverage differs from acquisition"
            )
        ranges = cast(list[JsonObject], selection["page_ranges"])
        if selected_keys is None and not ranges:
            summary = cast(JsonObject, manifest["summary"])
            expected_pages = sum(
                cast(int, artifact["pdf_page_count"]) for artifact in artifacts
            )
            if (
                summary["documents_expected"] != len(artifacts)
                or summary["pages_expected"] != expected_pages
            ):
                raise TranscriptionError(
                    "unfiltered page probe does not cover the acquisition corpus"
                )


def _validate_manifest(manifest: JsonObject, *, root: Path | None = None) -> None:
    try:
        schema = load_packaged_json("cadgpt_regulations.schemas", "page-probe.schema.json")
        validate_schema(manifest, schema, description="page probe")
    except ManifestError as exc:
        raise TranscriptionError(str(exc)) from exc
    configuration = cast(JsonObject, manifest["configuration"])
    configuration_values = dict(configuration)
    configuration_sha256 = cast(str, configuration_values.pop("sha256"))
    if sha256_json(configuration_values) != configuration_sha256:
        raise TranscriptionError("page probe configuration SHA-256 is false")
    toolchain = cast(JsonObject, manifest["toolchain"])
    toolchain_sha256 = cast(str, manifest["toolchain_sha256"])
    if sha256_json(toolchain) != toolchain_sha256:
        raise TranscriptionError("page probe toolchain SHA-256 is false")

    selection = cast(JsonObject, manifest["selection"])
    ranges = tuple(
        (cast(int, item["start"]), cast(int, item["end"]))
        for item in cast(list[JsonObject], selection["page_ranges"])
    )
    if ranges != _normalize_ranges(ranges):
        raise TranscriptionError("page probe ranges are not canonical")
    documents = cast(list[JsonObject], manifest["documents"])
    orders = [cast(int, document["catalog_order"]) for document in documents]
    keys = [cast(str, document["catalog_key"]) for document in documents]
    if orders != sorted(orders) or len(set(orders)) != len(orders):
        raise TranscriptionError("page probe documents are duplicated or reordered")
    if len(set(keys)) != len(keys):
        raise TranscriptionError("page probe document keys are duplicated")
    selected_keys = cast(list[str] | None, selection["catalog_keys"])
    if selected_keys is not None and set(selected_keys) != set(keys):
        raise TranscriptionError("page probe selection differs from its documents")

    for document in documents:
        source_sha256 = cast(str, document["source_sha256"])
        page_count = cast(int, document["pdf_page_count"])
        expected_pages = _selected_pages(page_count, ranges)
        pages = cast(list[JsonObject], document["pages"])
        actual_pages = tuple(cast(int, page["pdf_page"]) for page in pages)
        if actual_pages != expected_pages:
            raise TranscriptionError(
                "page probe pages are missing, duplicated, or reordered for "
                f"{document['catalog_key']}"
            )
        for page in pages:
            page_number = cast(int, page["pdf_page"])
            if page["page_id"] != _page_id(source_sha256, page_number):
                raise TranscriptionError("page probe page ID differs from its source/page")
            if page["state"] in {"ready", "needs_review"}:
                expected_path = (
                    Path("pages")
                    / source_sha256
                    / configuration_sha256
                    / toolchain_sha256
                    / f"{page_number:06d}"
                ).as_posix()
                if page["package_path"] != expected_path:
                    raise TranscriptionError("page package path has a false identity")
                if root is not None:
                    _validate_stored_package(
                        root,
                        page,
                        document=document,
                        configuration_sha256=configuration_sha256,
                        toolchain=toolchain,
                        toolchain_sha256=toolchain_sha256,
                    )

    pages = [
        page for document in documents for page in cast(list[JsonObject], document["pages"])
    ]
    if manifest["summary"] != _summarize(documents, pages):
        raise TranscriptionError("page probe summary differs from its records")


def _validate_stored_package(
    root: Path,
    page: JsonObject,
    *,
    document: JsonObject,
    configuration_sha256: str,
    toolchain: JsonObject,
    toolchain_sha256: str,
) -> None:
    try:
        package = safe_path(root, cast(str, page["package_path"]))
        snapshot = snapshot_directory(package)
        if tuple(entry.path for entry in snapshot.entries) != (
            "native.json",
            "page.json",
            "render.png",
        ):
            raise TranscriptionError("page package contains unexpected entries")
        page_path = safe_path(package, "page.json")
        page_snapshot = read_regular_snapshot(page_path)
        if page_snapshot.sha256 != page["package_sha256"]:
            raise TranscriptionError("page package manifest digest differs")
        package_record = load_object(page_path, description="page package")
        schema = load_packaged_json(
            "cadgpt_regulations.schemas", "page-package.schema.json"
        )
        validate_schema(package_record, schema, description="page package")
        source = cast(JsonObject, package_record["source"])
        if (
            package_record["page_id"] != page["page_id"]
            or source["catalog_key"] != document["catalog_key"]
            or source["catalog_order"] != document["catalog_order"]
            or source["sha256"] != document["source_sha256"]
            or source["bytes"] != document["source_bytes"]
            or source["pdf_page_count"] != document["pdf_page_count"]
            or source["pdf_page"] != page["pdf_page"]
            or package_record["configuration_sha256"] != configuration_sha256
            or package_record["toolchain"] != toolchain
            or package_record["toolchain_sha256"] != toolchain_sha256
            or package_record["state"] != page["state"]
            or package_record["classification"] != page["classification"]
            or package_record["route"] != page["route"]
            or package_record["reason_codes"] != page["reason_codes"]
            or package_record["metrics"] != page["metrics"]
        ):
            raise TranscriptionError("stored page package differs from its manifest record")
        for artifact in cast(list[JsonObject], package_record["artifacts"]):
            artifact_path = safe_path(root, cast(str, artifact["path"]))
            artifact_snapshot = read_regular_snapshot(artifact_path)
            if (
                artifact_snapshot.sha256 != artifact["sha256"]
                or artifact_snapshot.bytes != artifact["bytes"]
            ):
                raise TranscriptionError("stored page artifact failed re-attestation")
        artifacts = cast(list[JsonObject], package_record["artifacts"])
        roles = [cast(str, artifact["role"]) for artifact in artifacts]
        if roles != ["native_layout", "source_render"]:
            raise TranscriptionError("page package artifact roles are not exact and unique")
        expected_artifact_paths = [
            f"{page['package_path']}/native.json",
            f"{page['package_path']}/render.png",
        ]
        if [artifact["path"] for artifact in artifacts] != expected_artifact_paths:
            raise TranscriptionError("page package artifact paths are false")
        native_payload, _ = read_attested_bytes(
            safe_path(root, cast(str, artifacts[0]["path"])),
            expected_sha256=cast(str, artifacts[0]["sha256"]),
            expected_bytes=cast(int, artifacts[0]["bytes"]),
        )
        native = loads_object(
            native_payload.decode("utf-8"), description="native page layout"
        )
        _validate_native(native, page_id=cast(str, page["page_id"]))
    except (ManifestError, StorageError) as exc:
        raise TranscriptionError(str(exc)) from exc


def _validate_native(native: JsonObject, *, page_id: str) -> None:
    try:
        schema = load_packaged_json(
            "cadgpt_regulations.schemas", "native-layout.schema.json"
        )
        validate_schema(native, schema, description="native page layout")
    except ManifestError as exc:
        raise TranscriptionError(str(exc)) from exc
    if native["page_id"] != page_id:
        raise TranscriptionError("native page layout has a false page ID")
    for kind in ("chars", "words", "lines"):
        cells = cast(list[JsonObject], native[kind])
        expected_ids = [
            f"{page_id}:native:{kind[:-1] if kind.endswith('s') else kind}:{index:06d}"
            for index in range(len(cells))
        ]
        if [cell["span_id"] for cell in cells] != expected_ids:
            raise TranscriptionError(f"native {kind} span IDs are false or reordered")


def _install_package(root: Path, relative: Path, files: dict[str, bytes]) -> bool:
    try:
        ensure_private_tree(root, relative.parent.as_posix())
        destination = safe_path(root, relative.as_posix())
        temporary = make_temporary_directory(destination.parent, prefix=".page.")
        try:
            for name, payload in files.items():
                install_immutable_bytes(safe_path(temporary, name), payload)
            result = install_terminal_directory(
                temporary, destination, required_file="page.json"
            )
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return result.status is InstallStatus.INSTALLED
    except StorageError as exc:
        raise TranscriptionError(str(exc)) from exc


def _install_manifest(root: Path, manifest: JsonObject) -> tuple[Path, bool]:
    payload = canonical_bytes(manifest)
    digest = hashlib.sha256(payload).hexdigest()
    relative = Path("manifests") / "page-probe" / f"{digest}.json"
    index_relative = Path("indexes") / "page-probe" / f"{digest}.json"
    index: JsonObject = {
        "schema_version": "1.0.0",
        "kind": "page_probe",
        "manifest_path": relative.as_posix(),
        "manifest_sha256": digest,
        "configuration_sha256": cast(JsonObject, manifest["configuration"])["sha256"],
        "toolchain_sha256": manifest["toolchain_sha256"],
    }
    try:
        ensure_private_tree(root, relative.parent.as_posix())
        ensure_private_tree(root, index_relative.parent.as_posix())
        installed = install_immutable_bytes(safe_path(root, relative.as_posix()), payload)
        install_immutable_bytes(
            safe_path(root, index_relative.as_posix()), canonical_bytes(index)
        )
    except StorageError as exc:
        raise TranscriptionError(str(exc)) from exc
    return safe_path(root, relative.as_posix()), installed.status is InstallStatus.INSTALLED
