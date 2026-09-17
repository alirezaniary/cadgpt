"""Bounded official-source acquisition and deterministic receipt verification."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
import time
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import urljoin, urlsplit

import httpx

from cadgpt_regulations.catalog import load_catalog, validate_catalog
from cadgpt_regulations.errors import (
    AcquisitionError,
    CatalogError,
    InventoryError,
    ManifestError,
)
from cadgpt_regulations.inventory import write_inventory
from cadgpt_regulations.jsonio import (
    JsonObject,
    canonical_bytes,
    loads_object,
    sha256_json,
    validate_schema,
)
from cadgpt_regulations.pdf import detect_media_type, inspect_pdf
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.urlpolicy import (
    normalize_transport_url,
    validate_acquisition_url,
    validate_official_origins,
)

ACQUISITION_SCHEMA_VERSION = "2.0.0"
_READ_CHUNK_SIZE = 1024 * 1024
_PROBE_SIZE = 4096
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_JSON_MEDIA_TYPES = {"application/json", "application/ld+json"}
_CONTENT_LENGTH_PATTERN = re.compile(r"^[0-9]+$")
_SHA256_NAME_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_ACQUIRE_TEMP_PATTERN = re.compile(r"^\.acquire\.[A-Za-z0-9_-]+$")
_PROJECTION_TEMP_PATTERN = re.compile(r"^\.projection\.[A-Za-z0-9_-]+$")
_RECEIPT_TEMP_PATTERN = re.compile(r"^\.acquisition\.json\.[A-Za-z0-9_-]+\.tmp$")
_MANIFEST_TEMP_PATTERN = re.compile(r"^\.manifest\.json\.[A-Za-z0-9_-]+\.tmp$")


@dataclass(frozen=True)
class AcquisitionBlocker:
    subject: str
    code: str
    diagnostic: str


@dataclass(frozen=True)
class _FileSnapshot:
    digest: str
    byte_size: int
    prefix: bytes
    device: int
    inode: int
    modified_ns: int


@dataclass(frozen=True)
class _FetchResult:
    attempts: int
    resolved_url: str | None
    redirect_chain: tuple[str, ...]
    http_status: int | None
    header_media_type: str | None
    digest: str | None
    byte_size: int | None
    prefix: bytes
    temporary: Path | None
    error_code: str | None
    diagnostic: str | None


class _RenderedContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self.text: list[str] = []
        self.links: list[JsonObject] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        if self._anchor_href is not None:
            self._finish_anchor()
        self._anchor_href = dict(attrs).get("href")
        self._anchor_text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() == "a":
            self._finish_anchor()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._anchor_href is not None:
            self._finish_anchor()

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def close(self) -> None:
        super().close()
        if self._anchor_href is not None:
            self._finish_anchor()

    def _finish_anchor(self) -> None:
        href = self._anchor_href
        if href is not None and urlsplit(href).scheme.lower() in {"http", "https"}:
            self.links.append(
                {
                    "label": " ".join("".join(self._anchor_text).split()),
                    "href": href.strip(),
                }
            )
        self._anchor_href = None
        self._anchor_text = []


def acquire_corpus(
    output_root: Path,
    *,
    catalog: JsonObject | None = None,
    _testing_allowed_origins: frozenset[str] | None = None,
) -> JsonObject:
    """Acquire all configured sources and artifacts, recording every terminal result."""
    curated = load_catalog() if catalog is None else catalog
    validate_catalog(curated)
    directories = _prepare_output_root(output_root)
    policy = cast(JsonObject, curated["acquisition_policy"])
    allowed_origins = frozenset(cast(list[str], policy["allowed_origins"]))
    _validate_network_boundary(allowed_origins, _testing_allowed_origins)
    previous_receipt = _load_previous_receipt(
        output_root,
        curated,
        testing_allowed_origins=_testing_allowed_origins,
    )
    recovered_history = _recover_owned_temporaries(output_root, directories)
    _validate_startup_storage_index(
        output_root,
        previous_receipt=previous_receipt,
        recovered_history=recovered_history,
    )
    initial_transports = _prior_initial_transports(previous_receipt)
    timeout = httpx.Timeout(
        connect=float(policy["connect_timeout_seconds"]),
        read=float(policy["read_timeout_seconds"]),
        write=float(policy["read_timeout_seconds"]),
        pool=float(policy["connect_timeout_seconds"]),
    )
    metadata_results: list[JsonObject] = []
    artifact_results: list[JsonObject] = []

    with httpx.Client(
        follow_redirects=False,
        timeout=timeout,
        trust_env=False,
        headers={"User-Agent": "cadgpt-regulations/0.1", "Accept-Encoding": "identity"},
    ) as client:
        for source in cast(list[JsonObject], curated["metadata_sources"]):
            try:
                result = _acquire_metadata_source(
                    source,
                    client=client,
                    root=output_root,
                    raw_directory=directories["raw"],
                    projection_directory=directories["projections"],
                    quarantine_directory=directories["quarantine"],
                    policy=policy,
                    allowed_origins=allowed_origins,
                )
            except Exception as exc:  # noqa: BLE001
                result = _unexpected_metadata_result(source, exc)
            metadata_results.append(result)

        for artifact in cast(list[JsonObject], curated["artifacts"]):
            initial_transport = initial_transports.get(cast(str, artifact["catalog_key"]))
            try:
                result = _acquire_artifact(
                    artifact,
                    client=client,
                    root=output_root,
                    artifact_directory=directories["artifacts"],
                    quarantine_directory=directories["quarantine"],
                    policy=policy,
                    allowed_origins=allowed_origins,
                    initial_transport=initial_transport,
                )
            except Exception as exc:  # noqa: BLE001
                result = _unexpected_artifact_result(
                    artifact, exc, initial_transport=initial_transport
                )
            artifact_results.append(result)

    history = _build_history(
        output_root,
        previous_receipt=previous_receipt,
        recovered_history=recovered_history,
        metadata_results=metadata_results,
        artifact_results=artifact_results,
    )
    receipt: JsonObject = {
        "schema_version": ACQUISITION_SCHEMA_VERSION,
        "catalog": {
            "catalog_id": curated["catalog_id"],
            "schema_version": curated["schema_version"],
            "sha256": sha256_json(curated),
            "provenance": curated["provenance"],
        },
        "policy": policy,
        "summary": _summarize(metadata_results, artifact_results),
        "metadata_sources": metadata_results,
        "artifacts": artifact_results,
        "history": history,
    }
    validate_acquisition_receipt(
        receipt,
        catalog=curated,
        _testing_allowed_origins=_testing_allowed_origins,
    )
    write_acquisition_receipt(receipt, output_root / "acquisition.json")
    validate_acquisition_receipt(
        receipt,
        catalog=curated,
        root=output_root,
        _testing_allowed_origins=_testing_allowed_origins,
    )
    return receipt


def write_acquisition_receipt(receipt: JsonObject, output: Path) -> None:
    """Write a receipt using the package's canonical atomic JSON writer."""
    _require_private_directory(output.parent, "acquisition receipt directory")
    try:
        write_inventory(receipt, output)
    except InventoryError as exc:
        raise AcquisitionError(str(exc)) from exc


def validate_acquisition_receipt(
    receipt: JsonObject,
    *,
    catalog: JsonObject | None = None,
    root: Path | None = None,
    _testing_allowed_origins: frozenset[str] | None = None,
    _allow_legacy: bool = False,
) -> None:
    """Validate receipt schema, catalog binding, coverage, and stored payloads."""
    curated = load_catalog() if catalog is None else catalog
    validate_catalog(curated)
    allowed_origins = frozenset(
        cast(list[str], cast(JsonObject, curated["acquisition_policy"])["allowed_origins"])
    )
    _validate_network_boundary(allowed_origins, _testing_allowed_origins)
    try:
        schema = load_packaged_json("cadgpt_regulations.schemas", "acquisition.schema.json")
        validate_schema(receipt, schema, description="acquisition receipt")
    except ManifestError as exc:
        raise AcquisitionError(str(exc)) from exc
    if receipt["schema_version"] != ACQUISITION_SCHEMA_VERSION and not _allow_legacy:
        raise AcquisitionError(
            "legacy acquisition receipts are accepted only for unattended migration"
        )
    _validate_receipt_invariants(receipt, curated, allowed_origins=allowed_origins)
    if root is not None:
        _validate_receipt_storage(receipt, curated, root)


def check_acquisition_health(
    receipt: JsonObject,
    *,
    catalog: JsonObject | None = None,
    root: Path | None = None,
    _testing_allowed_origins: frozenset[str] | None = None,
) -> tuple[AcquisitionBlocker, ...]:
    """Return all terminal source/artifact failures after validating the receipt."""
    validate_acquisition_receipt(
        receipt,
        catalog=catalog,
        root=root,
        _testing_allowed_origins=_testing_allowed_origins,
    )
    blockers: list[AcquisitionBlocker] = []
    for source in cast(list[JsonObject], receipt["metadata_sources"]):
        if source["state"] != "ready":
            error = cast(JsonObject, source["error"])
            blockers.append(
                AcquisitionBlocker(
                    subject=cast(str, source["source_key"]),
                    code=cast(str, error["code"]),
                    diagnostic=cast(str, error["diagnostic"]),
                )
            )
    for artifact in cast(list[JsonObject], receipt["artifacts"]):
        if artifact["state"] != "ready":
            error = cast(JsonObject, artifact["error"])
            blockers.append(
                AcquisitionBlocker(
                    subject=cast(str, artifact["local_path"]),
                    code=cast(str, error["code"]),
                    diagnostic=cast(str, error["diagnostic"]),
                )
            )
    return tuple(blockers)


def project_wordpress_record(record: JsonObject) -> JsonObject:
    """Select stable WordPress fields and ordered HTTP(S) anchors."""
    wordpress_id = _required_int(record, "id")
    title = _required_object(record, "title")
    content = _required_object(record, "content")
    title_rendered = _required_string(title, "rendered")
    content_rendered = _required_string(content, "rendered")
    parser = _RenderedContentParser()
    parser.feed(content_rendered)
    parser.close()
    return {
        "wordpress_id": wordpress_id,
        "status": _required_string(record, "status"),
        "date": _required_string(record, "date"),
        "date_gmt": _required_string(record, "date_gmt"),
        "modified": _required_string(record, "modified"),
        "modified_gmt": _required_string(record, "modified_gmt"),
        "link": _required_string(record, "link"),
        "title_rendered": title_rendered,
        "content_rendered": content_rendered,
        "content_text": " ".join("".join(parser.text).split()),
        "document_links": parser.links,
    }


def semantic_projection(projection: JsonObject) -> JsonObject:
    """Remove markup-only variance while preserving all semantic source evidence."""
    links = [
        {
            "label": link["label"],
            "href": normalize_transport_url(cast(str, link["href"])),
        }
        for link in cast(list[JsonObject], projection["document_links"])
    ]
    return {
        "wordpress_id": projection["wordpress_id"],
        "status": projection["status"],
        "date": projection["date"],
        "date_gmt": projection["date_gmt"],
        "modified": projection["modified"],
        "modified_gmt": projection["modified_gmt"],
        "link": normalize_transport_url(cast(str, projection["link"])),
        "title_rendered": projection["title_rendered"],
        "content_text": projection["content_text"],
        "document_links": links,
    }


def _prepare_output_root(root: Path) -> dict[str, Path]:
    if not root.exists():
        raise AcquisitionError(
            "acquisition root must be created by the caller with private permissions: "
            f"{root}"
        )
    _require_private_directory(root, "acquisition root")
    paths = {
        "artifacts": root / "artifacts",
        "metadata": root / "metadata",
        "raw": root / "metadata" / "raw",
        "projections": root / "metadata" / "projections",
        "quarantine": root / "quarantine",
    }
    for label in ("artifacts", "metadata", "raw", "projections", "quarantine"):
        path = paths[label]
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise AcquisitionError(
                f"cannot create acquisition directory {path}: {exc}"
            ) from exc
        _require_private_directory(path, f"acquisition {label} directory")
    return paths


def _require_real_directory(path: Path, description: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise AcquisitionError(f"cannot inspect {description} {path}: {exc}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise AcquisitionError(f"{description} is not a real directory: {path}")


def _require_private_directory(path: Path, description: str) -> None:
    _require_real_directory(path, description)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise AcquisitionError(f"cannot inspect {description} {path}: {exc}") from exc
    if metadata.st_uid != os.geteuid():
        raise AcquisitionError(f"{description} is not owned by the current user: {path}")
    if metadata.st_mode & 0o022:
        raise AcquisitionError(f"{description} is group/world writable: {path}")


def _validate_network_boundary(
    configured_origins: frozenset[str],
    testing_allowed_origins: frozenset[str] | None,
) -> None:
    if testing_allowed_origins is None:
        try:
            validate_official_origins(configured_origins)
        except CatalogError as exc:
            raise AcquisitionError(str(exc)) from exc
        return
    if configured_origins != testing_allowed_origins:
        raise AcquisitionError(
            "test acquisition origins must exactly match the catalog policy"
        )


def _load_previous_receipt(
    root: Path,
    catalog: JsonObject,
    *,
    testing_allowed_origins: frozenset[str] | None,
) -> JsonObject | None:
    path = root / "acquisition.json"
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AcquisitionError(
            f"cannot inspect previous acquisition receipt: {_stable_os_diagnostic(exc)}"
        ) from exc
    snapshot = _read_regular_snapshot(path)
    try:
        payload = path.read_bytes()
        receipt = loads_object(
            payload.decode("utf-8"), description="previous acquisition receipt"
        )
    except (OSError, UnicodeError, ManifestError) as exc:
        raise AcquisitionError("previous acquisition receipt is invalid") from exc
    if (
        hashlib.sha256(payload).hexdigest() != snapshot.digest
        or not _snapshot_is_current(path, snapshot)
        or canonical_bytes(receipt) != payload
    ):
        raise AcquisitionError("previous acquisition receipt is not canonical or changed")
    validate_acquisition_receipt(
        receipt,
        catalog=catalog,
        _testing_allowed_origins=testing_allowed_origins,
        _allow_legacy=True,
    )
    return receipt


def _prior_initial_transports(
    previous_receipt: JsonObject | None,
) -> dict[str, JsonObject]:
    if previous_receipt is None:
        return {}
    transports: dict[str, JsonObject] = {}
    schema_version = cast(str, previous_receipt["schema_version"])
    for result in cast(list[JsonObject], previous_receipt["artifacts"]):
        value = result.get("initial_transport")
        if isinstance(value, dict):
            attestation = cast(JsonObject, value)
            transports[cast(str, result["catalog_key"])] = {
                **attestation,
                "redirect_chain": list(cast(list[str], attestation["redirect_chain"])),
            }
            continue
        if (
            schema_version == "1.0.0"
            and result["state"] == "ready"
            and result["action"] == "acquired"
        ):
            transports[cast(str, result["catalog_key"])] = {
                "requested_url": result["requested_url"],
                "resolved_url": result["resolved_url"],
                "redirect_chain": result["redirect_chain"],
                "attempts": result["attempts"],
                "http_status": result["http_status"],
                "sha256": result["sha256"],
                "bytes": result["bytes"],
                "detected_media_type": result["detected_media_type"],
                "pdf_page_count": result["pdf_page_count"],
            }
    return transports


def _recover_owned_temporaries(
    root: Path, directories: dict[str, Path]
) -> dict[str, list[JsonObject]]:
    candidates = (
        (root, _RECEIPT_TEMP_PATTERN, "acquisition-receipt"),
        (root, _MANIFEST_TEMP_PATTERN, "inventory-manifest"),
        (directories["artifacts"], _ACQUIRE_TEMP_PATTERN, "artifact-download"),
        (directories["raw"], _ACQUIRE_TEMP_PATTERN, "metadata-download"),
        (
            directories["projections"],
            _PROJECTION_TEMP_PATTERN,
            "metadata-projection",
        ),
    )
    recovered: dict[str, list[JsonObject]] = {}
    for directory, pattern, subject in candidates:
        try:
            entries = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            raise AcquisitionError(
                f"cannot enumerate interrupted writes: {_stable_os_diagnostic(exc)}"
            ) from exc
        for path in entries:
            if pattern.fullmatch(path.name) is None:
                continue
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise AcquisitionError(
                    f"cannot inspect interrupted write: {_stable_os_diagnostic(exc)}"
                ) from exc
            if (
                metadata.st_uid != os.geteuid()
                or stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
            ):
                continue
            snapshot = _read_regular_snapshot(path)
            destination = directories["quarantine"] / snapshot.digest
            original_path = _relative(root, path)
            if _recognized_temporary_subject(original_path) != subject:
                raise AcquisitionError(
                    f"interrupted-write classifier differs for {original_path}"
                )
            _install_temp_no_clobber(path, destination, snapshot.digest)
            destination_path = _relative(root, destination)
            recovered.setdefault(destination_path, []).append(
                {
                    "terminal_code": "INTERRUPTED_TEMP_RECOVERED",
                    "subject": subject,
                    "original_path": original_path,
                }
            )
    _reject_unknown_temporary_entries(root)
    return recovered


def _reject_unknown_temporary_entries(root: Path) -> None:
    directories = (
        root,
        root / "artifacts",
        root / "metadata",
        root / "metadata" / "raw",
        root / "metadata" / "projections",
        root / "quarantine",
    )
    for directory in directories:
        for path in directory.iterdir():
            if path.name.startswith("."):
                raise AcquisitionError(
                    f"unknown interrupted-write entry remains: {_relative(root, path)}"
                )


def _recognized_temporary_subject(value: str) -> str | None:
    parts = PurePosixPath(value).parts
    if len(parts) == 1:
        if _RECEIPT_TEMP_PATTERN.fullmatch(parts[0]) is not None:
            return "acquisition-receipt"
        if _MANIFEST_TEMP_PATTERN.fullmatch(parts[0]) is not None:
            return "inventory-manifest"
    if (
        len(parts) == 2
        and parts[0] == "artifacts"
        and _ACQUIRE_TEMP_PATTERN.fullmatch(parts[1]) is not None
    ):
        return "artifact-download"
    if (
        len(parts) == 3
        and parts[:2] == ("metadata", "raw")
        and _ACQUIRE_TEMP_PATTERN.fullmatch(parts[2]) is not None
    ):
        return "metadata-download"
    if (
        len(parts) == 3
        and parts[:2] == ("metadata", "projections")
        and _PROJECTION_TEMP_PATTERN.fullmatch(parts[2]) is not None
    ):
        return "metadata-projection"
    return None


def _validate_startup_storage_index(
    root: Path,
    *,
    previous_receipt: JsonObject | None,
    recovered_history: dict[str, list[JsonObject]],
) -> None:
    indexed = _prior_cas_records(previous_receipt)
    for value in recovered_history:
        snapshot = _read_regular_snapshot(_receipt_path(root, value))
        _merge_cas_record(
            indexed,
            path=value,
            digest=snapshot.digest,
            byte_size=snapshot.byte_size,
        )
    actual = _scan_content_addressed_storage(root)
    unindexed = sorted(set(actual) - set(indexed))
    if unindexed:
        raise AcquisitionError(
            f"unindexed content-addressed payloads are present: {unindexed!r}"
        )
    for path, record in indexed.items():
        _validate_cas_record(root, path, record)


def _build_history(
    root: Path,
    *,
    previous_receipt: JsonObject | None,
    recovered_history: dict[str, list[JsonObject]],
    metadata_results: list[JsonObject],
    artifact_results: list[JsonObject],
) -> list[JsonObject]:
    current = _current_cas_records(metadata_results, artifact_results)
    history: dict[str, JsonObject] = {}
    if previous_receipt is not None:
        for entry in cast(list[JsonObject], previous_receipt.get("history", [])):
            history[cast(str, entry["path"])] = {
                "storage_kind": entry["storage_kind"],
                "path": entry["path"],
                "sha256": entry["sha256"],
                "bytes": entry["bytes"],
                "origins": [
                    dict(origin) for origin in cast(list[JsonObject], entry["origins"])
                ],
            }
        for path, record in _prior_cas_records(previous_receipt).items():
            if path in current or path in history:
                continue
            _merge_history_entry(
                history,
                path=path,
                digest=cast(str, record["sha256"]),
                byte_size=cast(int, record["bytes"]),
                origins=cast(list[JsonObject], record.get("origins", [])),
            )
    for path, origins in recovered_history.items():
        snapshot = _read_regular_snapshot(_receipt_path(root, path))
        _merge_history_entry(
            history,
            path=path,
            digest=snapshot.digest,
            byte_size=snapshot.byte_size,
            origins=origins,
        )

    indexed = dict(current)
    for path, entry in history.items():
        _merge_cas_record(
            indexed,
            path=path,
            digest=cast(str, entry["sha256"]),
            byte_size=cast(int, entry["bytes"]),
        )
    actual = _scan_content_addressed_storage(root)
    unindexed = sorted(set(actual) - set(indexed))
    if unindexed:
        raise AcquisitionError(
            f"unindexed content-addressed payloads are present: {unindexed!r}"
        )
    missing = sorted(set(indexed) - set(actual))
    if missing:
        raise AcquisitionError(
            f"indexed content-addressed payloads are missing: {missing!r}"
        )
    for path, record in indexed.items():
        _validate_cas_record(root, path, record)

    result = list(history.values())
    for entry in result:
        origins = cast(list[JsonObject], entry["origins"])
        unique = {canonical_bytes(origin): origin for origin in origins}
        entry["origins"] = [unique[key] for key in sorted(unique)]
    return sorted(result, key=lambda entry: cast(str, entry["path"]))


def _prior_cas_records(previous_receipt: JsonObject | None) -> dict[str, JsonObject]:
    records: dict[str, JsonObject] = {}
    if previous_receipt is None:
        return records
    for entry in cast(list[JsonObject], previous_receipt.get("history", [])):
        _merge_cas_record(
            records,
            path=cast(str, entry["path"]),
            digest=cast(str, entry["sha256"]),
            byte_size=cast(int, entry["bytes"]),
        )
    for result in cast(list[JsonObject], previous_receipt["metadata_sources"]):
        subject = cast(str, result["source_key"])
        raw_path = cast(str | None, result["raw_path"])
        if raw_path is not None:
            _merge_cas_record(
                records,
                path=raw_path,
                digest=cast(str, result["raw_sha256"]),
                byte_size=cast(int, result["raw_bytes"]),
                origin=_prior_origin(subject),
            )
        projection_path = cast(str | None, result["projection_path"])
        if projection_path is not None:
            projection = cast(JsonObject, result["projection"])
            _merge_cas_record(
                records,
                path=projection_path,
                digest=cast(str, result["projection_sha256"]),
                byte_size=len(canonical_bytes(projection)),
                origin=_prior_origin(subject),
            )
        quarantine_path = cast(str | None, result["quarantine_path"])
        if quarantine_path is not None:
            _merge_cas_record(
                records,
                path=quarantine_path,
                digest=cast(str, result["raw_sha256"]),
                byte_size=cast(int, result["raw_bytes"]),
                origin=_prior_origin(subject),
            )
    for result in cast(list[JsonObject], previous_receipt["artifacts"]):
        quarantine_path = cast(str | None, result["quarantine_path"])
        if quarantine_path is not None:
            _merge_cas_record(
                records,
                path=quarantine_path,
                digest=cast(str, result["sha256"]),
                byte_size=cast(int, result["bytes"]),
                origin=_prior_origin(cast(str, result["catalog_key"])),
            )
    return records


def _current_cas_records(
    metadata_results: list[JsonObject], artifact_results: list[JsonObject]
) -> dict[str, JsonObject]:
    wrapper: JsonObject = {
        "history": [],
        "metadata_sources": metadata_results,
        "artifacts": artifact_results,
    }
    return _prior_cas_records(wrapper)


def _prior_origin(subject: str) -> JsonObject:
    return {
        "terminal_code": "RETAINED_PRIOR_EVIDENCE",
        "subject": subject,
        "original_path": None,
    }


def _merge_cas_record(
    records: dict[str, JsonObject],
    *,
    path: str,
    digest: str,
    byte_size: int,
    origin: JsonObject | None = None,
) -> None:
    existing = records.get(path)
    if existing is None:
        existing = {
            "sha256": digest,
            "bytes": byte_size,
            "origins": [],
        }
        records[path] = existing
    elif existing["sha256"] != digest or existing["bytes"] != byte_size:
        raise AcquisitionError(f"content-addressed index conflicts for {path}")
    if origin is not None:
        cast(list[JsonObject], existing["origins"]).append(origin)


def _merge_history_entry(
    history: dict[str, JsonObject],
    *,
    path: str,
    digest: str,
    byte_size: int,
    origins: list[JsonObject],
) -> None:
    storage_kind, path_digest = _cas_descriptor(path)
    if path_digest != digest:
        raise AcquisitionError(f"history path digest differs for {path}")
    entry = history.get(path)
    if entry is None:
        entry = {
            "storage_kind": storage_kind,
            "path": path,
            "sha256": digest,
            "bytes": byte_size,
            "origins": [],
        }
        history[path] = entry
    elif entry["sha256"] != digest or entry["bytes"] != byte_size:
        raise AcquisitionError(f"history index conflicts for {path}")
    cast(list[JsonObject], entry["origins"]).extend(dict(origin) for origin in origins)


def _scan_content_addressed_storage(root: Path) -> dict[str, _FileSnapshot]:
    actual: dict[str, _FileSnapshot] = {}
    directories = (
        root / "metadata" / "raw",
        root / "metadata" / "projections",
        root / "quarantine",
    )
    for directory in directories:
        for path in directory.iterdir():
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                raise AcquisitionError(
                    f"cannot inspect content-store entry: {_stable_os_diagnostic(exc)}"
                ) from exc
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                continue
            relative = _relative(root, path)
            try:
                _cas_descriptor(relative)
            except AcquisitionError:
                continue
            actual[relative] = _read_regular_snapshot(path)
    return actual


def _validate_cas_record(root: Path, path: str, record: JsonObject) -> None:
    _, path_digest = _cas_descriptor(path)
    digest = cast(str, record["sha256"])
    if path_digest != digest:
        raise AcquisitionError(f"content-addressed index path differs for {path}")
    snapshot = _read_regular_snapshot(_receipt_path(root, path))
    if snapshot.digest != digest or snapshot.byte_size != record["bytes"]:
        raise AcquisitionError(f"indexed content-addressed payload differs for {path}")


def _cas_descriptor(value: str) -> tuple[str, str]:
    parts = PurePosixPath(value).parts
    if len(parts) == 3 and parts[:2] == ("metadata", "raw"):
        filename = parts[2]
        digest = filename.removesuffix(".json")
        if filename.endswith(".json") and _SHA256_NAME_PATTERN.fullmatch(digest):
            return "metadata_raw", digest
    if len(parts) == 3 and parts[:2] == ("metadata", "projections"):
        filename = parts[2]
        digest = filename.removesuffix(".json")
        if filename.endswith(".json") and _SHA256_NAME_PATTERN.fullmatch(digest):
            return "metadata_projection", digest
    if (
        len(parts) == 2
        and parts[0] == "quarantine"
        and _SHA256_NAME_PATTERN.fullmatch(parts[1])
    ):
        return "quarantine", parts[1]
    raise AcquisitionError(f"path is not a content-addressed store entry: {value}")


def _acquire_metadata_source(
    source: JsonObject,
    *,
    client: httpx.Client,
    root: Path,
    raw_directory: Path,
    projection_directory: Path,
    quarantine_directory: Path,
    policy: JsonObject,
    allowed_origins: frozenset[str],
) -> JsonObject:
    requested_url = cast(str, source["requested_url"])
    base = _metadata_base(source)
    fetched = _fetch(
        client,
        requested_url,
        destination=raw_directory,
        max_bytes=cast(int, policy["max_metadata_bytes"]),
        max_attempts=cast(int, policy["max_attempts"]),
        max_redirects=cast(int, policy["max_redirects"]),
        total_timeout_seconds=float(policy["total_timeout_seconds"]),
        allowed_origins=allowed_origins,
        accept="application/json",
    )
    base.update(_fetch_fields(fetched))
    if fetched.error_code is not None:
        return _failed_metadata_from_fetch(
            base,
            fetched,
            root=root,
            quarantine_directory=quarantine_directory,
        )
    if fetched.http_status is None or not 200 <= fetched.http_status < 300:
        return _failed_metadata_payload(
            base,
            fetched,
            code="HTTP_STATUS_ERROR",
            diagnostic=f"metadata request returned HTTP {fetched.http_status}",
            root=root,
            quarantine_directory=quarantine_directory,
        )
    if fetched.header_media_type not in _JSON_MEDIA_TYPES:
        return _failed_metadata_payload(
            base,
            fetched,
            code="METADATA_MEDIA_TYPE_MISMATCH",
            diagnostic=(
                "expected JSON metadata, received "
                f"{fetched.header_media_type or 'no Content-Type'}"
            ),
            root=root,
            quarantine_directory=quarantine_directory,
        )
    if fetched.temporary is None or fetched.digest is None or fetched.byte_size is None:
        return _metadata_failure(base, "METADATA_BODY_MISSING", "metadata body is absent")

    try:
        raw_text = fetched.temporary.read_text(encoding="utf-8")
        raw_object = loads_object(raw_text, description="WordPress metadata response")
        projection = project_wordpress_record(raw_object)
    except (OSError, UnicodeError, ManifestError, AcquisitionError) as exc:
        return _failed_metadata_payload(
            base,
            fetched,
            code="METADATA_INVALID_RECORD",
            diagnostic=f"{type(exc).__name__}: metadata record is invalid",
            root=root,
            quarantine_directory=quarantine_directory,
        )

    if projection["wordpress_id"] != source["wordpress_id"]:
        return _failed_metadata_payload(
            base,
            fetched,
            code="METADATA_ID_MISMATCH",
            diagnostic=(
                f"expected WordPress id {source['wordpress_id']}, "
                f"received {projection['wordpress_id']}"
            ),
            root=root,
            quarantine_directory=quarantine_directory,
        )

    raw_path = raw_directory / f"{fetched.digest}.json"
    try:
        _install_temp_no_clobber(fetched.temporary, raw_path, fetched.digest)
    except AcquisitionError as exc:
        return _failed_metadata_payload(
            base,
            fetched,
            code="CONTENT_STORE_CONFLICT",
            diagnostic=str(exc),
            root=root,
            quarantine_directory=quarantine_directory,
        )

    projection_digest = sha256_json(projection)
    projection_path = projection_directory / f"{projection_digest}.json"
    projection_temp = _temporary_with_bytes(
        projection_directory, canonical_bytes(projection), prefix=".projection."
    )
    try:
        _install_temp_no_clobber(projection_temp, projection_path, projection_digest)
    except AcquisitionError as exc:
        _discard_temporary(projection_temp)
        return _metadata_failure(base, "CONTENT_STORE_CONFLICT", str(exc)) | {
            "raw_sha256": fetched.digest,
            "raw_bytes": fetched.byte_size,
            "raw_path": _relative(root, raw_path),
            "detected_media_type": fetched.header_media_type,
            "projection": projection,
            "projection_sha256": projection_digest,
        }

    semantic_digest = sha256_json(semantic_projection(projection))
    base.update(
        {
            "raw_sha256": fetched.digest,
            "raw_bytes": fetched.byte_size,
            "raw_path": _relative(root, raw_path),
            "detected_media_type": fetched.header_media_type,
            "projection": projection,
            "projection_sha256": projection_digest,
            "semantic_sha256": semantic_digest,
            "projection_path": _relative(root, projection_path),
            "quarantine_path": None,
        }
    )
    drift = _source_drift(source, projection, semantic_digest)
    if drift is not None:
        base["state"] = "quarantined"
        base["error"] = {"code": "SOURCE_DISCOVERY_DRIFT", "diagnostic": drift}
        return base
    base["state"] = "ready"
    base["error"] = None
    return base


def _metadata_base(source: JsonObject) -> JsonObject:
    return {
        "source_key": source["source_key"],
        "catalog_order": source["catalog_order"],
        "kind": source["kind"],
        "wordpress_id": source["wordpress_id"],
        "requested_url": source["requested_url"],
        "resolved_url": None,
        "redirect_chain": [],
        "attempts": 0,
        "http_status": None,
        "state": "quarantined",
        "raw_sha256": None,
        "raw_bytes": None,
        "raw_path": None,
        "detected_media_type": None,
        "projection": None,
        "projection_sha256": None,
        "semantic_sha256": None,
        "projection_path": None,
        "quarantine_path": None,
        "error": {"code": "NOT_ATTEMPTED", "diagnostic": "source was not attempted"},
    }


def _failed_metadata_from_fetch(
    base: JsonObject,
    fetched: _FetchResult,
    *,
    root: Path,
    quarantine_directory: Path,
) -> JsonObject:
    code = fetched.error_code or "HTTP_FETCH_FAILED"
    diagnostic = fetched.diagnostic or "metadata fetch failed"
    return _failed_metadata_payload(
        base,
        fetched,
        code=code,
        diagnostic=diagnostic,
        root=root,
        quarantine_directory=quarantine_directory,
    )


def _failed_metadata_payload(
    base: JsonObject,
    fetched: _FetchResult,
    *,
    code: str,
    diagnostic: str,
    root: Path,
    quarantine_directory: Path,
) -> JsonObject:
    quarantine_path, quarantine_note = _quarantine_fetch(
        fetched, root=root, quarantine_directory=quarantine_directory
    )
    base.update(
        {
            "raw_sha256": fetched.digest,
            "raw_bytes": fetched.byte_size,
            "detected_media_type": fetched.header_media_type,
            "quarantine_path": quarantine_path,
            "state": "quarantined",
            "error": {
                "code": code,
                "diagnostic": diagnostic + quarantine_note,
            },
        }
    )
    return base


def _metadata_failure(base: JsonObject, code: str, diagnostic: str) -> JsonObject:
    base["state"] = "quarantined"
    base["error"] = {"code": code, "diagnostic": diagnostic}
    return base


def _source_drift(
    source: JsonObject, projection: JsonObject, semantic_digest: str
) -> str | None:
    expected_digest = cast(str, source["expected_semantic_sha256"])
    expected_links = cast(list[JsonObject], source["expected_document_links"])
    actual_links = cast(list[JsonObject], projection["document_links"])
    normalized_expected = _normalized_links(expected_links)
    normalized_actual = _normalized_links(actual_links)
    problems: list[str] = []
    if semantic_digest != expected_digest:
        problems.append(
            f"semantic projection expected {expected_digest}, calculated {semantic_digest}"
        )
    if normalized_actual != normalized_expected:
        missing = list(
            (Counter(normalized_expected) - Counter(normalized_actual)).elements()
        )
        unexpected = list(
            (Counter(normalized_actual) - Counter(normalized_expected)).elements()
        )
        problems.append(
            "ordered document links differ; "
            f"expected={len(expected_links)}, discovered={len(actual_links)}, "
            f"missing={missing!r}, unexpected={unexpected!r}"
        )
    return "; ".join(problems) if problems else None


def _normalized_links(links: list[JsonObject]) -> list[tuple[str, str]]:
    return [
        (cast(str, link["label"]), normalize_transport_url(cast(str, link["href"])))
        for link in links
    ]


def _acquire_artifact(
    artifact: JsonObject,
    *,
    client: httpx.Client,
    root: Path,
    artifact_directory: Path,
    quarantine_directory: Path,
    policy: JsonObject,
    allowed_origins: frozenset[str],
    initial_transport: JsonObject | None,
) -> JsonObject:
    base = _artifact_base(artifact, initial_transport=initial_transport)
    target = artifact_directory / cast(str, artifact["local_path"])
    try:
        target.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        return _artifact_failure(
            base,
            "EXISTING_TARGET_INSPECTION_FAILED",
            _stable_os_diagnostic(exc),
        )
    else:
        existing = _reuse_or_reject_existing(base, target, artifact, root=root)
        if existing["state"] != "ready" or initial_transport is not None:
            return existing
        base = existing

    fetched = _fetch(
        client,
        cast(str, artifact["download_url"]),
        destination=artifact_directory,
        max_bytes=cast(int, policy["max_artifact_bytes"]),
        max_attempts=cast(int, policy["max_attempts"]),
        max_redirects=cast(int, policy["max_redirects"]),
        total_timeout_seconds=float(policy["total_timeout_seconds"]),
        allowed_origins=allowed_origins,
        accept="application/pdf",
    )
    base.update(_fetch_fields(fetched))
    base.update(
        {
            "sha256": fetched.digest,
            "bytes": fetched.byte_size,
            "detected_media_type": (
                detect_media_type(fetched.prefix) if fetched.byte_size is not None else None
            ),
        }
    )
    if fetched.error_code is not None:
        return _failed_artifact_payload(
            base,
            fetched,
            code=fetched.error_code,
            diagnostic=fetched.diagnostic or "artifact fetch failed",
            root=root,
            quarantine_directory=quarantine_directory,
        )
    if fetched.http_status is None or not 200 <= fetched.http_status < 300:
        return _failed_artifact_payload(
            base,
            fetched,
            code="HTTP_STATUS_ERROR",
            diagnostic=f"artifact request returned HTTP {fetched.http_status}",
            root=root,
            quarantine_directory=quarantine_directory,
        )
    if fetched.temporary is None or fetched.digest is None or fetched.byte_size is None:
        return _artifact_failure(base, "ARTIFACT_BODY_MISSING", "artifact body is absent")
    media_type = detect_media_type(fetched.prefix)
    if media_type != artifact["expected_media_type"]:
        return _failed_artifact_payload(
            base,
            fetched,
            code="MEDIA_TYPE_MISMATCH",
            diagnostic=f"expected application/pdf, detected {media_type}",
            root=root,
            quarantine_directory=quarantine_directory,
        )
    if fetched.digest != artifact["expected_sha256"]:
        return _failed_artifact_payload(
            base,
            fetched,
            code="SOURCE_HASH_MISMATCH",
            diagnostic=(
                f"expected SHA-256 {artifact['expected_sha256']}, "
                f"calculated {fetched.digest}"
            ),
            root=root,
            quarantine_directory=quarantine_directory,
        )
    if fetched.byte_size != artifact["expected_bytes"]:
        return _failed_artifact_payload(
            base,
            fetched,
            code="SOURCE_SIZE_MISMATCH",
            diagnostic=(
                f"expected {artifact['expected_bytes']} bytes, received {fetched.byte_size}"
            ),
            root=root,
            quarantine_directory=quarantine_directory,
        )

    probe = inspect_pdf(fetched.temporary)
    base["pdf_page_count"] = probe.page_count
    if probe.error_code is not None:
        return _failed_artifact_payload(
            base,
            fetched,
            code=probe.error_code,
            diagnostic=probe.diagnostic or "pdfinfo failed",
            root=root,
            quarantine_directory=quarantine_directory,
        )
    if probe.page_count != artifact["expected_pdf_pages"]:
        return _failed_artifact_payload(
            base,
            fetched,
            code="PDF_PAGE_COUNT_MISMATCH",
            diagnostic=(
                f"expected {artifact['expected_pdf_pages']} PDF pages, "
                f"found {probe.page_count}"
            ),
            root=root,
            quarantine_directory=quarantine_directory,
        )

    try:
        _install_temp_no_clobber(fetched.temporary, target, fetched.digest)
    except AcquisitionError as exc:
        return _failed_artifact_payload(
            base,
            fetched,
            code="EXISTING_TARGET_CONFLICT",
            diagnostic=str(exc),
            root=root,
            quarantine_directory=quarantine_directory,
        )
    base.update(
        {
            "state": "ready",
            "action": "acquired",
            "artifact_path": _relative(root, target),
            "quarantine_path": None,
            "error": None,
        }
    )
    if base["initial_transport"] is None:
        base["initial_transport"] = _initial_transport_attestation(
            fetched,
            media_type=media_type,
            page_count=cast(int, probe.page_count),
        )
    return base


def _artifact_base(
    artifact: JsonObject, *, initial_transport: JsonObject | None = None
) -> JsonObject:
    return {
        "catalog_key": artifact["catalog_key"],
        "catalog_order": artifact["catalog_order"],
        "download_url": artifact["download_url"],
        "requested_url": artifact["download_url"],
        "resolved_url": None,
        "redirect_chain": [],
        "remote_filename": artifact["remote_filename"],
        "local_path": artifact["local_path"],
        "expected_sha256": artifact["expected_sha256"],
        "expected_bytes": artifact["expected_bytes"],
        "expected_media_type": artifact["expected_media_type"],
        "expected_pdf_pages": artifact["expected_pdf_pages"],
        "attempts": 0,
        "http_status": None,
        "initial_transport": initial_transport,
        "state": "quarantined",
        "action": "none",
        "sha256": None,
        "bytes": None,
        "detected_media_type": None,
        "pdf_page_count": None,
        "artifact_path": None,
        "quarantine_path": None,
        "error": {"code": "NOT_ATTEMPTED", "diagnostic": "artifact was not attempted"},
    }


def _initial_transport_attestation(
    fetched: _FetchResult, *, media_type: str, page_count: int
) -> JsonObject:
    return {
        "requested_url": fetched.redirect_chain[0],
        "resolved_url": cast(str, fetched.resolved_url),
        "redirect_chain": list(fetched.redirect_chain),
        "attempts": fetched.attempts,
        "http_status": cast(int, fetched.http_status),
        "sha256": cast(str, fetched.digest),
        "bytes": cast(int, fetched.byte_size),
        "detected_media_type": media_type,
        "pdf_page_count": page_count,
    }


def _reuse_or_reject_existing(
    base: JsonObject, target: Path, artifact: JsonObject, *, root: Path
) -> JsonObject:
    try:
        snapshot = _read_regular_snapshot(target)
    except AcquisitionError as exc:
        return _artifact_failure(base, "UNSAFE_EXISTING_TARGET", str(exc))
    media_type = detect_media_type(snapshot.prefix)
    base.update(
        {
            "sha256": snapshot.digest,
            "bytes": snapshot.byte_size,
            "detected_media_type": media_type,
        }
    )
    mismatch = _expected_file_mismatch(snapshot, media_type, artifact)
    if mismatch is not None:
        return _artifact_failure(base, "EXISTING_TARGET_CONFLICT", mismatch)
    probe = inspect_pdf(target)
    base["pdf_page_count"] = probe.page_count
    if probe.error_code is not None:
        return _artifact_failure(
            base,
            "EXISTING_TARGET_CONFLICT",
            probe.diagnostic or "existing target failed pdfinfo",
        )
    if probe.page_count != artifact["expected_pdf_pages"]:
        return _artifact_failure(
            base,
            "EXISTING_TARGET_CONFLICT",
            (
                f"existing target has {probe.page_count} pages; "
                f"expected {artifact['expected_pdf_pages']}"
            ),
        )
    if not _snapshot_is_current(target, snapshot):
        return _artifact_failure(
            base,
            "EXISTING_TARGET_CHANGED",
            "existing target changed while it was being attested",
        )
    base.update(
        {
            "state": "ready",
            "action": "reused",
            "artifact_path": _relative(root, target),
            "error": None,
        }
    )
    return base


def _expected_file_mismatch(
    snapshot: _FileSnapshot, media_type: str, artifact: JsonObject
) -> str | None:
    if media_type != artifact["expected_media_type"]:
        return f"existing target is {media_type}, expected application/pdf"
    if snapshot.digest != artifact["expected_sha256"]:
        return (
            f"existing target SHA-256 is {snapshot.digest}, "
            f"expected {artifact['expected_sha256']}"
        )
    if snapshot.byte_size != artifact["expected_bytes"]:
        return (
            f"existing target has {snapshot.byte_size} bytes, "
            f"expected {artifact['expected_bytes']}"
        )
    return None


def _failed_artifact_payload(
    base: JsonObject,
    fetched: _FetchResult,
    *,
    code: str,
    diagnostic: str,
    root: Path,
    quarantine_directory: Path,
) -> JsonObject:
    quarantine_path, quarantine_note = _quarantine_fetch(
        fetched, root=root, quarantine_directory=quarantine_directory
    )
    base.update(
        {
            "state": "quarantined",
            "action": "none",
            "artifact_path": None,
            "quarantine_path": quarantine_path,
            "error": {"code": code, "diagnostic": diagnostic + quarantine_note},
        }
    )
    return base


def _artifact_failure(base: JsonObject, code: str, diagnostic: str) -> JsonObject:
    base.update(
        {
            "state": "quarantined",
            "action": "none",
            "artifact_path": None,
            "error": {"code": code, "diagnostic": diagnostic},
        }
    )
    return base


def _fetch(
    client: httpx.Client,
    requested_url: str,
    *,
    destination: Path,
    max_bytes: int,
    max_attempts: int,
    max_redirects: int,
    total_timeout_seconds: float,
    allowed_origins: frozenset[str],
    accept: str,
) -> _FetchResult:
    last: _FetchResult | None = None
    deadline = time.monotonic() + total_timeout_seconds
    for attempt in range(1, max_attempts + 1):
        if time.monotonic() >= deadline:
            if last is not None:
                return _replace_fetch_error(
                    last,
                    code="TOTAL_TIMEOUT_EXCEEDED",
                    diagnostic="total acquisition deadline exceeded",
                )
            return _empty_fetch_failure(
                0,
                None,
                [],
                "TOTAL_TIMEOUT_EXCEEDED",
                "total acquisition deadline elapsed before the first request",
            )
        result = _fetch_once(
            client,
            requested_url,
            destination=destination,
            max_bytes=max_bytes,
            max_redirects=max_redirects,
            deadline=deadline,
            allowed_origins=allowed_origins,
            accept=accept,
            attempt=attempt,
        )
        retryable = (
            result.error_code
            in {
                "HTTP_TRANSPORT_ERROR",
                "HTTP_STREAM_ERROR",
                "HTTP_LENGTH_MISMATCH",
            }
            or result.http_status in _RETRY_STATUSES
        )
        if not retryable:
            return result
        if time.monotonic() >= deadline:
            return _replace_fetch_error(
                result,
                code="TOTAL_TIMEOUT_EXCEEDED",
                diagnostic="total acquisition deadline exceeded",
            )
        if attempt < max_attempts:
            if result.temporary is not None:
                _discard_temporary(result.temporary)
            last = result
            continue
        if result.error_code is not None:
            return _FetchResult(
                attempts=attempt,
                resolved_url=result.resolved_url,
                redirect_chain=result.redirect_chain,
                http_status=result.http_status,
                header_media_type=result.header_media_type,
                digest=result.digest,
                byte_size=result.byte_size,
                prefix=result.prefix,
                temporary=result.temporary,
                error_code="HTTP_RETRY_EXHAUSTED",
                diagnostic=f"request failed after {attempt} attempts",
            )
        return result
    if last is not None:
        return last
    return _FetchResult(
        attempts=0,
        resolved_url=None,
        redirect_chain=(),
        http_status=None,
        header_media_type=None,
        digest=None,
        byte_size=None,
        prefix=b"",
        temporary=None,
        error_code="HTTP_RETRY_EXHAUSTED",
        diagnostic="request was not attempted",
    )


def _replace_fetch_error(
    result: _FetchResult, *, code: str, diagnostic: str
) -> _FetchResult:
    return _FetchResult(
        attempts=result.attempts,
        resolved_url=result.resolved_url,
        redirect_chain=result.redirect_chain,
        http_status=result.http_status,
        header_media_type=result.header_media_type,
        digest=result.digest,
        byte_size=result.byte_size,
        prefix=result.prefix,
        temporary=result.temporary,
        error_code=code,
        diagnostic=diagnostic,
    )


def _bounded_timeout(configured: httpx.Timeout, deadline: float) -> httpx.Timeout:
    remaining = max(0.001, deadline - time.monotonic())

    def bounded(value: float | None) -> float:
        return remaining if value is None else min(value, remaining)

    return httpx.Timeout(
        connect=bounded(configured.connect),
        read=bounded(configured.read),
        write=bounded(configured.write),
        pool=bounded(configured.pool),
    )


def _fetch_once(
    client: httpx.Client,
    requested_url: str,
    *,
    destination: Path,
    max_bytes: int,
    max_redirects: int,
    deadline: float,
    allowed_origins: frozenset[str],
    accept: str,
    attempt: int,
) -> _FetchResult:
    current = requested_url
    chain: list[str] = []
    for redirect_count in range(max_redirects + 1):
        if time.monotonic() >= deadline:
            chain.append(current)
            return _empty_fetch_failure(
                attempt,
                current,
                chain,
                "TOTAL_TIMEOUT_EXCEEDED",
                "total acquisition deadline exceeded",
            )
        try:
            validate_acquisition_url(current, allowed_origins)
        except CatalogError as exc:
            return _empty_fetch_failure(
                attempt,
                current,
                chain,
                "UNAPPROVED_ORIGIN",
                str(exc),
            )
        chain.append(current)
        try:
            with client.stream(
                "GET",
                current,
                headers={"Accept": accept},
                timeout=_bounded_timeout(client.timeout, deadline),
            ) as response:
                status = response.status_code
                media_type = _header_media_type(response.headers.get("Content-Type"))
                if status in _REDIRECT_STATUSES:
                    location = response.headers.get("Location")
                    if location is None:
                        return _empty_fetch_failure(
                            attempt,
                            current,
                            chain,
                            "INVALID_REDIRECT",
                            f"HTTP {status} response omitted Location",
                            http_status=status,
                            media_type=media_type,
                        )
                    target = urljoin(current, location)
                    chain.append(target)
                    try:
                        validate_acquisition_url(target, allowed_origins)
                    except CatalogError:
                        return _empty_fetch_failure(
                            attempt,
                            current,
                            chain,
                            "UNAPPROVED_REDIRECT",
                            f"redirect target has an unapproved origin: {target}",
                            http_status=status,
                            media_type=media_type,
                        )
                    if redirect_count == max_redirects:
                        return _empty_fetch_failure(
                            attempt,
                            current,
                            chain,
                            "TOO_MANY_REDIRECTS",
                            f"redirect limit {max_redirects} exceeded",
                            http_status=status,
                            media_type=media_type,
                        )
                    chain.pop()
                    current = target
                    continue
                encoding = response.headers.get("Content-Encoding", "identity").lower()
                if encoding not in {"", "identity"}:
                    return _empty_fetch_failure(
                        attempt,
                        current,
                        chain,
                        "UNSUPPORTED_CONTENT_ENCODING",
                        f"unsupported Content-Encoding: {encoding}",
                        http_status=status,
                        media_type=media_type,
                    )
                try:
                    declared_length = _content_length(
                        response.headers.get("Content-Length")
                    )
                except ValueError:
                    return _empty_fetch_failure(
                        attempt,
                        current,
                        chain,
                        "INVALID_CONTENT_LENGTH",
                        "response Content-Length is not a non-negative decimal integer",
                        http_status=status,
                        media_type=media_type,
                    )
                if declared_length is not None and declared_length > max_bytes:
                    return _empty_fetch_failure(
                        attempt,
                        current,
                        chain,
                        "BODY_TOO_LARGE",
                        f"declared body size {declared_length} exceeds limit {max_bytes}",
                        http_status=status,
                        media_type=media_type,
                    )
                return _stream_response(
                    response,
                    attempt=attempt,
                    current=current,
                    chain=chain,
                    destination=destination,
                    max_bytes=max_bytes,
                    declared_length=declared_length,
                    media_type=media_type,
                    deadline=deadline,
                )
        except httpx.TimeoutException:
            deadline_exceeded = time.monotonic() >= deadline
            return _empty_fetch_failure(
                attempt,
                current,
                chain,
                "TOTAL_TIMEOUT_EXCEEDED" if deadline_exceeded else "HTTP_TRANSPORT_ERROR",
                (
                    "total acquisition deadline exceeded"
                    if deadline_exceeded
                    else "TimeoutException: request timed out"
                ),
            )
        except httpx.TransportError as exc:
            return _empty_fetch_failure(
                attempt,
                current,
                chain,
                "HTTP_TRANSPORT_ERROR",
                f"{type(exc).__name__}: transport failed",
            )
    return _empty_fetch_failure(
        attempt,
        current,
        chain,
        "TOO_MANY_REDIRECTS",
        f"redirect limit {max_redirects} exceeded",
    )


def _stream_response(
    response: httpx.Response,
    *,
    attempt: int,
    current: str,
    chain: list[str],
    destination: Path,
    max_bytes: int,
    declared_length: int | None,
    media_type: str | None,
    deadline: float,
) -> _FetchResult:
    _require_private_directory(destination, "acquisition payload directory")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".acquire.", dir=destination)
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    byte_size = 0
    prefix = b""
    try:
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            try:
                for chunk in response.iter_raw():
                    if time.monotonic() >= deadline:
                        output.flush()
                        os.fsync(output.fileno())
                        return _fetch_with_payload_error(
                            attempt,
                            current,
                            chain,
                            response.status_code,
                            media_type,
                            digest,
                            byte_size,
                            prefix,
                            temporary,
                            "TOTAL_TIMEOUT_EXCEEDED",
                            "total acquisition deadline exceeded",
                        )
                    if byte_size + len(chunk) > max_bytes:
                        output.flush()
                        os.fsync(output.fileno())
                        return _fetch_with_payload_error(
                            attempt,
                            current,
                            chain,
                            response.status_code,
                            media_type,
                            digest,
                            byte_size,
                            prefix,
                            temporary,
                            "BODY_TOO_LARGE",
                            f"streamed body exceeds limit {max_bytes}",
                        )
                    if len(prefix) < _PROBE_SIZE:
                        prefix += chunk[: _PROBE_SIZE - len(prefix)]
                    output.write(chunk)
                    digest.update(chunk)
                    byte_size += len(chunk)
                if time.monotonic() >= deadline:
                    output.flush()
                    os.fsync(output.fileno())
                    return _fetch_with_payload_error(
                        attempt,
                        current,
                        chain,
                        response.status_code,
                        media_type,
                        digest,
                        byte_size,
                        prefix,
                        temporary,
                        "TOTAL_TIMEOUT_EXCEEDED",
                        "total acquisition deadline exceeded",
                    )
            except httpx.TimeoutException:
                output.flush()
                os.fsync(output.fileno())
                deadline_exceeded = time.monotonic() >= deadline
                return _fetch_with_payload_error(
                    attempt,
                    current,
                    chain,
                    response.status_code,
                    media_type,
                    digest,
                    byte_size,
                    prefix,
                    temporary,
                    (
                        "TOTAL_TIMEOUT_EXCEEDED"
                        if deadline_exceeded
                        else "HTTP_STREAM_ERROR"
                    ),
                    (
                        "total acquisition deadline exceeded"
                        if deadline_exceeded
                        else "TimeoutException: response body timed out"
                    ),
                )
            except httpx.TransportError as exc:
                output.flush()
                os.fsync(output.fileno())
                return _fetch_with_payload_error(
                    attempt,
                    current,
                    chain,
                    response.status_code,
                    media_type,
                    digest,
                    byte_size,
                    prefix,
                    temporary,
                    "HTTP_STREAM_ERROR",
                    f"{type(exc).__name__}: response body failed",
                )
            output.flush()
            os.fsync(output.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if declared_length is not None and byte_size != declared_length:
        return _fetch_with_payload_error(
            attempt,
            current,
            chain,
            response.status_code,
            media_type,
            digest,
            byte_size,
            prefix,
            temporary,
            "HTTP_LENGTH_MISMATCH",
            f"Content-Length declared {declared_length}, received {byte_size}",
        )
    return _FetchResult(
        attempts=attempt,
        resolved_url=current,
        redirect_chain=tuple(chain),
        http_status=response.status_code,
        header_media_type=media_type,
        digest=digest.hexdigest(),
        byte_size=byte_size,
        prefix=prefix,
        temporary=temporary,
        error_code=None,
        diagnostic=None,
    )


def _fetch_with_payload_error(
    attempt: int,
    current: str,
    chain: list[str],
    status: int,
    media_type: str | None,
    digest: Any,
    byte_size: int,
    prefix: bytes,
    temporary: Path,
    code: str,
    diagnostic: str,
) -> _FetchResult:
    return _FetchResult(
        attempts=attempt,
        resolved_url=current,
        redirect_chain=tuple(chain),
        http_status=status,
        header_media_type=media_type,
        digest=digest.hexdigest(),
        byte_size=byte_size,
        prefix=prefix,
        temporary=temporary,
        error_code=code,
        diagnostic=diagnostic,
    )


def _empty_fetch_failure(
    attempt: int,
    resolved_url: str | None,
    chain: list[str],
    code: str,
    diagnostic: str,
    *,
    http_status: int | None = None,
    media_type: str | None = None,
) -> _FetchResult:
    return _FetchResult(
        attempts=attempt,
        resolved_url=resolved_url,
        redirect_chain=tuple(chain),
        http_status=http_status,
        header_media_type=media_type,
        digest=None,
        byte_size=None,
        prefix=b"",
        temporary=None,
        error_code=code,
        diagnostic=diagnostic,
    )


def _fetch_fields(fetched: _FetchResult) -> JsonObject:
    return {
        "resolved_url": fetched.resolved_url,
        "redirect_chain": list(fetched.redirect_chain),
        "attempts": fetched.attempts,
        "http_status": fetched.http_status,
    }


def _header_media_type(value: str | None) -> str | None:
    if value is None:
        return None
    media_type = value.partition(";")[0].strip().lower()
    return media_type or None


def _content_length(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.strip()
    if _CONTENT_LENGTH_PATTERN.fullmatch(normalized) is None:
        raise ValueError("invalid Content-Length")
    return int(normalized)


def _quarantine_fetch(
    fetched: _FetchResult, *, root: Path, quarantine_directory: Path
) -> tuple[str | None, str]:
    if fetched.temporary is None or fetched.digest is None:
        return None, ""
    destination = quarantine_directory / fetched.digest
    try:
        _install_temp_no_clobber(fetched.temporary, destination, fetched.digest)
    except AcquisitionError as exc:
        _discard_temporary(fetched.temporary)
        return None, f"; quarantine failed: {exc}"
    return _relative(root, destination), ""


def _install_temp_no_clobber(
    temporary: Path, destination: Path, expected_digest: str
) -> bool:
    _require_private_directory(temporary.parent, "temporary payload directory")
    _require_private_directory(destination.parent, "payload installation directory")
    try:
        temporary_snapshot = _read_regular_snapshot(temporary)
    except AcquisitionError as exc:
        raise AcquisitionError(f"cannot attest temporary payload: {exc}") from exc
    if temporary_snapshot.digest != expected_digest:
        _discard_temporary(temporary)
        raise AcquisitionError("temporary payload digest differs from expected content")
    try:
        os.link(temporary, destination, follow_symlinks=False)
    except FileExistsError:
        try:
            existing = _read_regular_snapshot(destination)
        except AcquisitionError as exc:
            raise AcquisitionError(
                f"existing destination is unsafe: {destination.name}: {exc}"
            ) from exc
        if existing.digest != expected_digest:
            raise AcquisitionError(
                f"existing destination differs and was not overwritten: {destination.name}"
            ) from None
        _discard_temporary(temporary)
        return False
    except OSError as exc:
        raise AcquisitionError(
            f"cannot install payload {destination.name}: {_stable_os_diagnostic(exc)}"
        ) from exc

    installed_identity = (temporary_snapshot.device, temporary_snapshot.inode)
    try:
        _require_private_directory(destination.parent, "payload installation directory")
        installed = destination.lstat()
        if (
            not stat.S_ISREG(installed.st_mode)
            or stat.S_ISLNK(installed.st_mode)
            or (installed.st_dev, installed.st_ino) != installed_identity
        ):
            raise AcquisitionError(
                f"installed payload identity changed unexpectedly: {destination.name}"
            )
        try:
            temporary.unlink()
        except OSError as exc:
            raise AcquisitionError(
                "cannot remove temporary payload after installation: "
                f"{_stable_os_diagnostic(exc)}"
            ) from exc
        _fsync_directory(destination.parent)
        if temporary.parent != destination.parent:
            _fsync_directory(temporary.parent)
        installed_snapshot = _read_regular_snapshot(destination)
        if (
            installed_snapshot.digest != expected_digest
            or (installed_snapshot.device, installed_snapshot.inode) != installed_identity
        ):
            raise AcquisitionError(
                f"installed payload failed post-install attestation: {destination.name}"
            )
    except (AcquisitionError, OSError):
        _unlink_if_identity(destination, installed_identity)
        _discard_temporary(temporary)
        with suppress(OSError):
            _fsync_directory(destination.parent)
        raise
    return True


def _unlink_if_identity(path: Path, identity: tuple[int, int]) -> None:
    try:
        current = path.lstat()
        if (
            stat.S_ISREG(current.st_mode)
            and not stat.S_ISLNK(current.st_mode)
            and (current.st_dev, current.st_ino) == identity
        ):
            path.unlink()
    except OSError:
        return


def _temporary_with_bytes(directory: Path, payload: bytes, *, prefix: str) -> Path:
    _require_private_directory(directory, "acquisition content-store directory")
    descriptor, temporary_name = tempfile.mkstemp(prefix=prefix, dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return temporary


def _discard_temporary(path: Path) -> None:
    with suppress(OSError):
        path.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_regular_snapshot(path: Path) -> _FileSnapshot:
    try:
        initial = path.lstat()
    except OSError as exc:
        raise AcquisitionError(_stable_os_diagnostic(exc)) from exc
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise AcquisitionError("path is not a regular file")
    if initial.st_nlink != 1:
        raise AcquisitionError("path must have exactly one hard link")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AcquisitionError(_stable_os_diagnostic(exc)) from exc
    digest = hashlib.sha256()
    prefix = b""
    byte_size = 0
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise AcquisitionError("path is not a regular file")
        if before.st_nlink != 1:
            raise AcquisitionError("path must have exactly one hard link")
        while chunk := os.read(descriptor, _READ_CHUNK_SIZE):
            if len(prefix) < _PROBE_SIZE:
                prefix += chunk[: _PROBE_SIZE - len(prefix)]
            digest.update(chunk)
            byte_size += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or byte_size != after.st_size:
        raise AcquisitionError("file changed while it was being read")
    snapshot = _FileSnapshot(
        digest=digest.hexdigest(),
        byte_size=byte_size,
        prefix=prefix,
        device=after.st_dev,
        inode=after.st_ino,
        modified_ns=after.st_mtime_ns,
    )
    if not _snapshot_is_current(path, snapshot):
        raise AcquisitionError("file identity changed immediately after it was read")
    return snapshot


def _snapshot_is_current(path: Path, snapshot: _FileSnapshot) -> bool:
    try:
        current = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(current.st_mode)
        and not stat.S_ISLNK(current.st_mode)
        and current.st_nlink == 1
        and (
            current.st_dev,
            current.st_ino,
            current.st_size,
            current.st_mtime_ns,
        )
        == (
            snapshot.device,
            snapshot.inode,
            snapshot.byte_size,
            snapshot.modified_ns,
        )
    )


def _summarize(
    metadata_results: list[JsonObject], artifact_results: list[JsonObject]
) -> JsonObject:
    ready_artifacts = [
        artifact for artifact in artifact_results if artifact["state"] == "ready"
    ]
    return {
        "metadata_expected": len(metadata_results),
        "metadata_ready": sum(source["state"] == "ready" for source in metadata_results),
        "metadata_quarantined": sum(
            source["state"] == "quarantined" for source in metadata_results
        ),
        "artifacts_expected": len(artifact_results),
        "artifacts_ready": len(ready_artifacts),
        "artifacts_acquired": sum(
            artifact["action"] == "acquired" for artifact in ready_artifacts
        ),
        "artifacts_reused": sum(
            artifact["action"] == "reused" for artifact in ready_artifacts
        ),
        "artifacts_quarantined": sum(
            artifact["state"] == "quarantined" for artifact in artifact_results
        ),
        "pdf_pages": sum(
            cast(int, artifact["pdf_page_count"]) for artifact in ready_artifacts
        ),
        "bytes": sum(cast(int, artifact["bytes"]) for artifact in ready_artifacts),
    }


def _validate_receipt_invariants(
    receipt: JsonObject,
    catalog: JsonObject,
    *,
    allowed_origins: frozenset[str],
) -> None:
    schema_version = cast(str, receipt["schema_version"])
    identity = cast(JsonObject, receipt["catalog"])
    if identity != {
        "catalog_id": catalog["catalog_id"],
        "schema_version": catalog["schema_version"],
        "sha256": sha256_json(catalog),
        "provenance": catalog["provenance"],
    }:
        raise AcquisitionError("acquisition receipt catalog identity does not match")
    if receipt["policy"] != catalog["acquisition_policy"]:
        raise AcquisitionError("acquisition receipt policy does not match the catalog")

    results = cast(list[JsonObject], receipt["metadata_sources"])
    expected_sources = cast(list[JsonObject], catalog["metadata_sources"])
    if len(results) != len(expected_sources):
        raise AcquisitionError("acquisition receipt metadata coverage differs")
    for expected, actual in zip(expected_sources, results, strict=True):
        for field in ("source_key", "catalog_order", "kind", "wordpress_id"):
            if actual[field] != expected[field]:
                raise AcquisitionError(
                    f"metadata result {actual['source_key']} differs at {field}"
                )
        if actual["requested_url"] != expected["requested_url"]:
            raise AcquisitionError(
                f"metadata result {actual['source_key']} differs at requested_url"
            )
        _validate_result_transport(
            actual,
            requested_url=cast(str, expected["requested_url"]),
            allowed_origins=allowed_origins,
            max_attempts=cast(int, cast(JsonObject, receipt["policy"])["max_attempts"]),
            max_redirects=cast(int, cast(JsonObject, receipt["policy"])["max_redirects"]),
            allow_reuse=False,
        )
        projection_value = actual["projection"]
        projection_fields = (
            actual["projection_sha256"],
            actual["semantic_sha256"],
            actual["projection_path"],
        )
        if projection_value is None and any(
            value is not None for value in projection_fields
        ):
            raise AcquisitionError(
                f"metadata projection fields are incomplete for {actual['source_key']}"
            )
        if projection_value is not None:
            if any(value is None for value in projection_fields):
                raise AcquisitionError(
                    f"metadata projection fields are incomplete for {actual['source_key']}"
                )
            projection = cast(JsonObject, projection_value)
            if sha256_json(projection) != actual["projection_sha256"]:
                raise AcquisitionError(
                    f"metadata projection digest differs for {actual['source_key']}"
                )
            semantic_digest = sha256_json(semantic_projection(projection))
            if semantic_digest != actual["semantic_sha256"]:
                raise AcquisitionError(
                    f"metadata semantic digest differs for {actual['source_key']}"
                )
            drift = _source_drift(expected, projection, semantic_digest)
            if actual["state"] == "ready" and drift is not None:
                raise AcquisitionError(
                    f"ready metadata source {actual['source_key']} has discovery drift"
                )
            if actual["state"] == "quarantined":
                error = cast(JsonObject, actual["error"])
                if error["code"] == "SOURCE_DISCOVERY_DRIFT" and drift is None:
                    raise AcquisitionError(
                        f"metadata source {actual['source_key']} claims absent "
                        "discovery drift"
                    )
        if (actual["raw_sha256"] is None) != (actual["raw_bytes"] is None):
            raise AcquisitionError(
                "metadata raw digest and size differ in presence for "
                f"{actual['source_key']}"
            )
        if actual["raw_path"] is not None and actual["raw_sha256"] is None:
            raise AcquisitionError(
                f"metadata raw path lacks a digest for {actual['source_key']}"
            )
        if actual["quarantine_path"] is not None and actual["raw_sha256"] is None:
            raise AcquisitionError(
                f"metadata quarantine path lacks a digest for {actual['source_key']}"
            )

    artifact_results = cast(list[JsonObject], receipt["artifacts"])
    expected_artifacts = cast(list[JsonObject], catalog["artifacts"])
    if len(artifact_results) != len(expected_artifacts):
        raise AcquisitionError("acquisition receipt artifact coverage differs")
    copied = (
        "catalog_key",
        "catalog_order",
        "download_url",
        "remote_filename",
        "local_path",
        "expected_sha256",
        "expected_bytes",
        "expected_media_type",
        "expected_pdf_pages",
    )
    for expected, actual in zip(expected_artifacts, artifact_results, strict=True):
        for field in copied:
            if actual[field] != expected[field]:
                raise AcquisitionError(
                    f"artifact result {actual['catalog_key']} differs at {field}"
                )
        if actual["requested_url"] != expected["download_url"]:
            raise AcquisitionError(
                f"artifact result {actual['catalog_key']} differs at requested_url"
            )
        _validate_result_transport(
            actual,
            requested_url=cast(str, expected["download_url"]),
            allowed_origins=allowed_origins,
            max_attempts=cast(int, cast(JsonObject, receipt["policy"])["max_attempts"]),
            max_redirects=cast(int, cast(JsonObject, receipt["policy"])["max_redirects"]),
            allow_reuse=True,
        )
        initial_transport = actual.get("initial_transport")
        if (
            schema_version == ACQUISITION_SCHEMA_VERSION
            and actual["state"] == "ready"
            and not isinstance(initial_transport, dict)
        ):
            raise AcquisitionError(
                f"ready artifact {actual['catalog_key']} lacks initial transport evidence"
            )
        if isinstance(initial_transport, dict):
            _validate_initial_transport(
                cast(JsonObject, initial_transport),
                artifact=expected,
                allowed_origins=allowed_origins,
                max_attempts=cast(int, cast(JsonObject, receipt["policy"])["max_attempts"]),
                max_redirects=cast(
                    int, cast(JsonObject, receipt["policy"])["max_redirects"]
                ),
            )
        if actual["state"] == "ready" and any(
            actual[field] != expected[expected_field]
            for field, expected_field in (
                ("sha256", "expected_sha256"),
                ("bytes", "expected_bytes"),
                ("detected_media_type", "expected_media_type"),
                ("pdf_page_count", "expected_pdf_pages"),
            )
        ):
            raise AcquisitionError(
                f"ready artifact {actual['catalog_key']} differs from its pinned contract"
            )
        if (actual["sha256"] is None) != (actual["bytes"] is None):
            raise AcquisitionError(
                f"artifact digest and size differ in presence for {actual['catalog_key']}"
            )
        if actual["quarantine_path"] is not None and actual["sha256"] is None:
            raise AcquisitionError(
                f"artifact quarantine path lacks a digest for {actual['catalog_key']}"
            )
    _validate_history_index(receipt, catalog)
    expected_summary = _summarize(results, artifact_results)
    if receipt["summary"] != expected_summary:
        raise AcquisitionError("acquisition receipt summary does not match its records")


def _validate_result_transport(
    result: JsonObject,
    *,
    requested_url: str,
    allowed_origins: frozenset[str],
    max_attempts: int,
    max_redirects: int,
    allow_reuse: bool,
) -> None:
    subject = cast(str, result.get("catalog_key", result.get("source_key", "result")))
    attempts = cast(int, result["attempts"])
    status = cast(int | None, result["http_status"])
    resolved = cast(str | None, result["resolved_url"])
    chain = cast(list[str], result["redirect_chain"])
    state = cast(str, result["state"])
    action = cast(str | None, result.get("action"))
    error = cast(JsonObject | None, result["error"])
    error_code = None if error is None else cast(str, error["code"])

    if attempts > max_attempts:
        raise AcquisitionError(f"receipt attempts exceed policy for {subject}")

    reused = allow_reuse and state == "ready" and action == "reused"
    if reused:
        if attempts != 0 or status is not None or resolved is not None or chain:
            raise AcquisitionError(f"reused artifact claims network activity for {subject}")
        return

    if state == "ready":
        if attempts < 1:
            raise AcquisitionError(f"ready result was not fetched for {subject}")
        if status is None or not 200 <= status < 300:
            raise AcquisitionError(
                f"ready result lacks a successful HTTP status for {subject}"
            )
        if allow_reuse and action != "acquired":
            raise AcquisitionError(f"ready artifact has an invalid action for {subject}")

    if attempts == 0:
        if status is not None or resolved is not None or chain:
            raise AcquisitionError(
                f"unattempted result claims network activity for {subject}"
            )
        if state == "ready":
            raise AcquisitionError(f"ready result was not attempted for {subject}")
        if error_code not in {
            "INTERNAL_ACQUISITION_ERROR",
            "EXISTING_TARGET_CHANGED",
            "EXISTING_TARGET_CONFLICT",
            "EXISTING_TARGET_INSPECTION_FAILED",
            "TOTAL_TIMEOUT_EXCEEDED",
            "UNSAFE_EXISTING_TARGET",
        }:
            raise AcquisitionError(f"unattempted result has an invalid error for {subject}")
        return

    if not chain or chain[0] != requested_url or resolved is None:
        raise AcquisitionError(f"receipt URL chain is incoherent for {subject}")

    trailing_target = error_code in {"TOO_MANY_REDIRECTS", "UNAPPROVED_REDIRECT"}
    if trailing_target:
        if len(chain) < 2 or chain[-2] != resolved or status not in _REDIRECT_STATUSES:
            raise AcquisitionError(f"terminal redirect chain is incoherent for {subject}")
        approved_hops = chain[:-1]
    else:
        if chain[-1] != resolved:
            raise AcquisitionError(
                f"resolved URL differs from redirect chain for {subject}"
            )
        approved_hops = chain

    maximum_chain_length = max_redirects + (2 if trailing_target else 1)
    if len(chain) > maximum_chain_length:
        raise AcquisitionError(f"receipt redirect chain exceeds policy for {subject}")
    for hop in approved_hops:
        try:
            validate_acquisition_url(hop, allowed_origins)
        except CatalogError as exc:
            raise AcquisitionError(
                f"receipt URL origin is unapproved for {subject}"
            ) from exc

    if error_code == "UNAPPROVED_REDIRECT":
        try:
            validate_acquisition_url(chain[-1], allowed_origins)
        except CatalogError:
            pass
        else:
            raise AcquisitionError(
                f"unapproved redirect error has an approved target for {subject}"
            )
    elif trailing_target:
        try:
            validate_acquisition_url(chain[-1], allowed_origins)
        except CatalogError as exc:
            raise AcquisitionError(
                f"receipt URL origin is unapproved for {subject}"
            ) from exc

    if status is None and error_code not in {
        "HTTP_RETRY_EXHAUSTED",
        "HTTP_TRANSPORT_ERROR",
        "TOTAL_TIMEOUT_EXCEEDED",
    }:
        raise AcquisitionError(f"attempted result lacks an HTTP status for {subject}")
    if error_code == "HTTP_STATUS_ERROR" and status is not None and 200 <= status < 300:
        raise AcquisitionError(f"HTTP status error claims success for {subject}")


def _validate_initial_transport(
    attestation: JsonObject,
    *,
    artifact: JsonObject,
    allowed_origins: frozenset[str],
    max_attempts: int,
    max_redirects: int,
) -> None:
    subject = cast(str, artifact["catalog_key"])
    requested_url = cast(str, artifact["download_url"])
    chain = cast(list[str], attestation["redirect_chain"])
    if attestation["requested_url"] != requested_url:
        raise AcquisitionError(f"initial transport requested URL differs for {subject}")
    if not chain or chain[0] != requested_url or chain[-1] != attestation["resolved_url"]:
        raise AcquisitionError(f"initial transport URL chain is incoherent for {subject}")
    if len(chain) > max_redirects + 1:
        raise AcquisitionError(
            f"initial transport redirect chain exceeds policy for {subject}"
        )
    attempts = cast(int, attestation["attempts"])
    if not 1 <= attempts <= max_attempts:
        raise AcquisitionError(f"initial transport attempts exceed policy for {subject}")
    status = cast(int, attestation["http_status"])
    if not 200 <= status < 300:
        raise AcquisitionError(
            f"initial transport lacks a successful HTTP status for {subject}"
        )
    for hop in chain:
        try:
            validate_acquisition_url(hop, allowed_origins)
        except CatalogError as exc:
            raise AcquisitionError(
                f"initial transport URL origin is unapproved for {subject}"
            ) from exc
    for field, expected_field in (
        ("sha256", "expected_sha256"),
        ("bytes", "expected_bytes"),
        ("detected_media_type", "expected_media_type"),
        ("pdf_page_count", "expected_pdf_pages"),
    ):
        if attestation[field] != artifact[expected_field]:
            raise AcquisitionError(
                f"initial transport {field} differs from the pinned contract for {subject}"
            )


def _validate_history_index(receipt: JsonObject, catalog: JsonObject) -> None:
    if receipt["schema_version"] != ACQUISITION_SCHEMA_VERSION:
        return
    history = cast(list[JsonObject], receipt["history"])
    paths = [cast(str, entry["path"]) for entry in history]
    if paths != sorted(set(paths)):
        raise AcquisitionError("acquisition history paths are not unique and ordered")

    retained_subjects = {
        cast(str, source["source_key"])
        for source in cast(list[JsonObject], catalog["metadata_sources"])
    } | {
        cast(str, artifact["catalog_key"])
        for artifact in cast(list[JsonObject], catalog["artifacts"])
    }
    for entry in history:
        path = cast(str, entry["path"])
        storage_kind, path_digest = _cas_descriptor(path)
        if storage_kind != entry["storage_kind"] or path_digest != entry["sha256"]:
            raise AcquisitionError(f"acquisition history identity differs for {path}")
        origins = cast(list[JsonObject], entry["origins"])
        encoded_origins = [canonical_bytes(origin) for origin in origins]
        if encoded_origins != sorted(set(encoded_origins)):
            raise AcquisitionError(
                f"acquisition history origins are not unique and ordered for {path}"
            )
        for origin in origins:
            terminal_code = cast(str, origin["terminal_code"])
            subject = cast(str, origin["subject"])
            original_path = cast(str | None, origin["original_path"])
            if terminal_code == "RETAINED_PRIOR_EVIDENCE":
                if subject not in retained_subjects or original_path is not None:
                    raise AcquisitionError(
                        f"retained acquisition history origin is invalid for {path}"
                    )
                continue
            if (
                original_path is None
                or _recognized_temporary_subject(original_path) != subject
            ):
                raise AcquisitionError(
                    f"recovered acquisition history origin is invalid for {path}"
                )

    _prior_cas_records(receipt)


def _validate_receipt_storage(receipt: JsonObject, catalog: JsonObject, root: Path) -> None:
    _require_private_directory(root, "acquisition root")
    managed_directories = {
        "artifacts": root / "artifacts",
        "metadata": root / "metadata",
        "metadata/raw": root / "metadata" / "raw",
        "metadata/projections": root / "metadata" / "projections",
        "quarantine": root / "quarantine",
    }
    for relative, directory in managed_directories.items():
        _require_private_directory(directory, f"acquisition {relative} directory")

    receipt_path = root / "acquisition.json"
    receipt_snapshot = _read_regular_snapshot(receipt_path)
    expected_receipt = canonical_bytes(receipt)
    if receipt_snapshot.digest != hashlib.sha256(
        expected_receipt
    ).hexdigest() or receipt_snapshot.byte_size != len(expected_receipt):
        raise AcquisitionError("stored acquisition receipt differs from supplied receipt")

    expected_paths: set[str] = {"acquisition.json", *managed_directories}
    allowed_unsupported: set[str] = set()
    manifest_path = root / "manifest.json"
    try:
        manifest_path.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise AcquisitionError(
            f"cannot inspect adjacent manifest: {_stable_os_diagnostic(exc)}"
        ) from exc
    else:
        _read_regular_snapshot(manifest_path)
        expected_paths.add("manifest.json")
    _account_content_addressed_storage(receipt, root, expected_paths)
    for expected, result in zip(
        cast(list[JsonObject], catalog["metadata_sources"]),
        cast(list[JsonObject], receipt["metadata_sources"]),
        strict=True,
    ):
        raw_path = cast(str | None, result["raw_path"])
        projection_path = cast(str | None, result["projection_path"])
        quarantine_path = cast(str | None, result["quarantine_path"])
        for value in (raw_path, projection_path, quarantine_path):
            if value is not None:
                expected_paths.add(value)
        if raw_path is not None:
            raw_file = _receipt_path(root, raw_path)
            raw_snapshot = _read_regular_snapshot(raw_file)
            if (
                raw_snapshot.digest != result["raw_sha256"]
                or raw_snapshot.byte_size != result["raw_bytes"]
                or raw_path != f"metadata/raw/{raw_snapshot.digest}.json"
            ):
                raise AcquisitionError(
                    f"metadata raw snapshot digest differs for {result['source_key']}"
                )
            if projection_path is not None:
                try:
                    raw_object = loads_object(
                        raw_file.read_text(encoding="utf-8"),
                        description="stored WordPress metadata",
                    )
                    derived = project_wordpress_record(raw_object)
                except (OSError, UnicodeError, ManifestError) as exc:
                    raise AcquisitionError(
                        f"stored WordPress metadata is invalid for {result['source_key']}"
                    ) from exc
                if derived != result["projection"]:
                    raise AcquisitionError(
                        f"stored WordPress projection differs for {result['source_key']}"
                    )
                semantic_digest = sha256_json(semantic_projection(derived))
                if (
                    result["state"] == "ready"
                    and _source_drift(expected, derived, semantic_digest) is not None
                ):
                    raise AcquisitionError(
                        f"stored WordPress source has drift for {result['source_key']}"
                    )
        if projection_path is not None:
            projection_file = _receipt_path(root, projection_path)
            snapshot = _read_regular_snapshot(projection_file)
            if (
                snapshot.digest != result["projection_sha256"]
                or projection_path != f"metadata/projections/{snapshot.digest}.json"
                or projection_file.read_bytes()
                != canonical_bytes(cast(JsonObject, result["projection"]))
            ):
                raise AcquisitionError(
                    f"stored projection differs for {result['source_key']}"
                )
        if quarantine_path is not None:
            _validate_quarantine_path(
                result, root, quarantine_path, "raw_sha256", "raw_bytes"
            )

    for expected, result in zip(
        cast(list[JsonObject], catalog["artifacts"]),
        cast(list[JsonObject], receipt["artifacts"]),
        strict=True,
    ):
        artifact_path = cast(str | None, result["artifact_path"])
        quarantine_path = cast(str | None, result["quarantine_path"])
        for value in (artifact_path, quarantine_path):
            if value is not None:
                expected_paths.add(value)
        if artifact_path is not None:
            if artifact_path != f"artifacts/{expected['local_path']}":
                raise AcquisitionError(
                    f"artifact storage path differs for {result['catalog_key']}"
                )
            path = _receipt_path(root, artifact_path)
            snapshot = _read_regular_snapshot(path)
            media_type = detect_media_type(snapshot.prefix)
            probe = inspect_pdf(path)
            if (
                snapshot.digest != expected["expected_sha256"]
                or snapshot.byte_size != expected["expected_bytes"]
                or media_type != expected["expected_media_type"]
                or probe.error_code is not None
                or probe.page_count != expected["expected_pdf_pages"]
            ):
                raise AcquisitionError(
                    f"stored artifact differs for {result['catalog_key']}"
                )
        if quarantine_path is not None:
            _validate_quarantine_path(result, root, quarantine_path, "sha256", "bytes")

        if result["state"] == "quarantined":
            error = cast(JsonObject, result["error"])
            target_value = f"artifacts/{expected['local_path']}"
            target = _receipt_path(root, target_value)
            try:
                target_metadata = target.lstat()
            except FileNotFoundError:
                pass
            except OSError as exc:
                if error["code"] != "EXISTING_TARGET_INSPECTION_FAILED":
                    raise AcquisitionError(
                        f"cannot inspect failed artifact target {target_value}: "
                        f"{_stable_os_diagnostic(exc)}"
                    ) from exc
            else:
                expected_paths.add(target_value)
                if stat.S_ISLNK(target_metadata.st_mode) or not stat.S_ISREG(
                    target_metadata.st_mode
                ):
                    allowed_unsupported.add(target_value)
                _validate_failed_existing_target(result, target, target_metadata, expected)

    _reject_unaccounted_storage(
        root, expected_paths, allowed_unsupported=allowed_unsupported
    )


def _validate_quarantine_path(
    result: JsonObject,
    root: Path,
    value: str,
    digest_field: str,
    bytes_field: str,
) -> None:
    digest = cast(str | None, result[digest_field])
    if digest is None or value != f"quarantine/{digest}":
        raise AcquisitionError("quarantine path is not content-addressed")
    snapshot = _read_regular_snapshot(_receipt_path(root, value))
    if snapshot.digest != digest or snapshot.byte_size != result[bytes_field]:
        raise AcquisitionError("quarantine payload digest differs")


def _account_content_addressed_storage(
    receipt: JsonObject, root: Path, expected_paths: set[str]
) -> None:
    for entry in cast(list[JsonObject], receipt.get("history", [])):
        path = cast(str, entry["path"])
        _validate_cas_record(root, path, entry)
        expected_paths.add(path)


def _validate_failed_existing_target(
    result: JsonObject,
    target: Path,
    target_metadata: os.stat_result,
    expected: JsonObject,
) -> None:
    error = cast(JsonObject, result["error"])
    error_code = cast(str, error["code"])
    is_regular = (
        stat.S_ISREG(target_metadata.st_mode)
        and not stat.S_ISLNK(target_metadata.st_mode)
        and target_metadata.st_nlink == 1
    )
    if not is_regular:
        return
    snapshot = _read_regular_snapshot(target)
    media_type = detect_media_type(snapshot.prefix)
    if error_code == "EXISTING_TARGET_CONFLICT":
        expected_digest = result["sha256"]
        expected_bytes = result["bytes"]
        expected_media_type = result["detected_media_type"]
        expected_pages = cast(int | None, result["pdf_page_count"])
    else:
        expected_digest = expected["expected_sha256"]
        expected_bytes = expected["expected_bytes"]
        expected_media_type = expected["expected_media_type"]
        expected_pages = cast(int, expected["expected_pdf_pages"])
    if (
        snapshot.digest != expected_digest
        or snapshot.byte_size != expected_bytes
        or media_type != expected_media_type
    ):
        raise AcquisitionError(
            f"failed existing target differs for {result['catalog_key']}"
        )
    if expected_pages is None:
        return
    probe = inspect_pdf(target)
    if probe.error_code is not None or probe.page_count != expected_pages:
        raise AcquisitionError(
            f"failed existing target page count differs for {result['catalog_key']}"
        )


def _reject_unaccounted_storage(
    root: Path,
    expected_paths: set[str],
    *,
    allowed_unsupported: set[str],
) -> None:
    actual: set[str] = set()
    unsupported: list[str] = []

    def visit(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            raise AcquisitionError(
                f"cannot enumerate acquisition storage: {_stable_os_diagnostic(exc)}"
            ) from exc
        for path in entries:
            relative = path.relative_to(root).as_posix()
            actual.add(relative)
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                raise AcquisitionError(
                    f"cannot inspect acquisition storage entry {relative}: "
                    f"{_stable_os_diagnostic(exc)}"
                ) from exc
            if stat.S_ISDIR(mode) and not stat.S_ISLNK(mode):
                visit(path)
            elif not stat.S_ISREG(mode) or stat.S_ISLNK(mode):
                unsupported.append(relative)

    visit(root)
    extra = sorted(actual - expected_paths)
    missing = sorted(expected_paths - actual)
    unexpected_unsupported = sorted(set(unsupported) - allowed_unsupported)
    if extra or missing or unexpected_unsupported:
        raise AcquisitionError(
            "acquisition storage coverage differs; "
            f"missing={missing!r}, extra={extra!r}, "
            f"unsupported={unexpected_unsupported!r}"
        )


def _receipt_path(root: Path, value: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise AcquisitionError(f"unsafe receipt path: {value!r}")
    candidate = root.joinpath(*relative.parts)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AcquisitionError(f"receipt path escapes acquisition root: {value!r}") from exc
    return candidate


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise AcquisitionError(f"path escapes acquisition root: {path}") from exc


def _required_object(value: JsonObject, key: str) -> JsonObject:
    item = value.get(key)
    if not isinstance(item, dict):
        raise AcquisitionError(f"WordPress field {key} must be an object")
    return cast(JsonObject, item)


def _required_string(value: JsonObject, key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise AcquisitionError(f"WordPress field {key} must be a string")
    return item


def _required_int(value: JsonObject, key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise AcquisitionError(f"WordPress field {key} must be an integer")
    return item


def _unexpected_metadata_result(source: JsonObject, exc: Exception) -> JsonObject:
    return _metadata_failure(
        _metadata_base(source),
        "INTERNAL_ACQUISITION_ERROR",
        f"{type(exc).__name__}: source processing failed",
    )


def _unexpected_artifact_result(
    artifact: JsonObject,
    exc: Exception,
    *,
    initial_transport: JsonObject | None,
) -> JsonObject:
    return _artifact_failure(
        _artifact_base(artifact, initial_transport=initial_transport),
        "INTERNAL_ACQUISITION_ERROR",
        f"{type(exc).__name__}: artifact processing failed",
    )


def _stable_os_diagnostic(exc: OSError) -> str:
    return f"{type(exc).__name__}: {exc.strerror or 'operating system error'}"
