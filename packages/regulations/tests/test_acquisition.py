from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from copy import deepcopy
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest
from cadgpt_regulations.acquisition import (
    AcquisitionBlocker,
    project_wordpress_record,
    semantic_projection,
)
from cadgpt_regulations.acquisition import (
    acquire_corpus as _acquire_corpus,
)
from cadgpt_regulations.acquisition import (
    check_acquisition_health as _check_acquisition_health,
)
from cadgpt_regulations.acquisition import (
    validate_acquisition_receipt as _validate_acquisition_receipt,
)
from cadgpt_regulations.catalog import load_catalog, validate_catalog
from cadgpt_regulations.cli import main
from cadgpt_regulations.errors import AcquisitionError, CatalogError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes, sha256_json


@dataclass
class _Route:
    body: bytes = b""
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    delay_seconds: float = 0
    truncate_at: int | None = None
    chunk_size: int | None = None
    chunk_delay_seconds: float = 0


@dataclass
class _LocalServer:
    origin: str
    routes: dict[str, _Route]
    requests: Counter[str]


@contextmanager
def _serve() -> Iterator[_LocalServer]:
    routes: dict[str, _Route] = {}
    requests: Counter[str] = Counter()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests[self.path] += 1
            route = routes.get(self.path, _Route(body=b"not found", status=404))
            self.send_response(route.status)
            headers = dict(route.headers)
            headers.setdefault("Content-Length", str(len(route.body)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            if route.delay_seconds:
                time.sleep(route.delay_seconds)
            payload = (
                route.body[: route.truncate_at]
                if route.truncate_at is not None
                else route.body
            )
            with suppress(BrokenPipeError, ConnectionResetError):
                if route.chunk_size is None:
                    self.wfile.write(payload)
                    self.wfile.flush()
                else:
                    for offset in range(0, len(payload), route.chunk_size):
                        self.wfile.write(payload[offset : offset + route.chunk_size])
                        self.wfile.flush()
                        time.sleep(route.chunk_delay_seconds)

        def log_message(self, format: str, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    host, port = httpd.server_address
    server = _LocalServer(f"http://{host}:{port}", routes, requests)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture
def local_server() -> Iterator[_LocalServer]:
    with _serve() as server:
        yield server


def _testing_origins(catalog: JsonObject) -> frozenset[str]:
    policy = cast(JsonObject, catalog["acquisition_policy"])
    return frozenset(cast(list[str], policy["allowed_origins"]))


def acquire_corpus(output_root: Path, *, catalog: JsonObject) -> JsonObject:
    output_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    output_root.chmod(0o700)
    return _acquire_corpus(
        output_root,
        catalog=catalog,
        _testing_allowed_origins=_testing_origins(catalog),
    )


def check_acquisition_health(
    receipt: JsonObject, *, catalog: JsonObject, root: Path
) -> tuple[AcquisitionBlocker, ...]:
    return _check_acquisition_health(
        receipt,
        catalog=catalog,
        root=root,
        _testing_allowed_origins=_testing_origins(catalog),
    )


def validate_acquisition_receipt(
    receipt: JsonObject, *, catalog: JsonObject, root: Path | None = None
) -> None:
    _validate_acquisition_receipt(
        receipt,
        catalog=catalog,
        root=root,
        _testing_allowed_origins=_testing_origins(catalog),
    )


def test_complete_acquisition_is_attested_and_second_run_reuses_without_rewrite(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    root = tmp_path / "acquisition"

    first = acquire_corpus(root, catalog=catalog)
    first_mtimes = {
        cast(str, artifact["local_path"]): (
            root / "artifacts" / cast(str, artifact["local_path"])
        )
        .stat()
        .st_mtime_ns
        for artifact in cast(list[JsonObject], catalog["artifacts"])
    }

    assert first["summary"] == {
        "metadata_expected": 9,
        "metadata_ready": 9,
        "metadata_quarantined": 0,
        "artifacts_expected": 43,
        "artifacts_ready": 43,
        "artifacts_acquired": 43,
        "artifacts_reused": 0,
        "artifacts_quarantined": 0,
        "pdf_pages": 43,
        "bytes": len(pdf) * 43,
    }
    first_transports = {
        cast(str, artifact["catalog_key"]): deepcopy(artifact["initial_transport"])
        for artifact in cast(list[JsonObject], first["artifacts"])
    }
    for artifact in cast(list[JsonObject], first["artifacts"]):
        assert artifact["initial_transport"] == {
            "requested_url": artifact["requested_url"],
            "resolved_url": artifact["resolved_url"],
            "redirect_chain": artifact["redirect_chain"],
            "attempts": artifact["attempts"],
            "http_status": artifact["http_status"],
            "sha256": artifact["sha256"],
            "bytes": artifact["bytes"],
            "detected_media_type": artifact["detected_media_type"],
            "pdf_page_count": artifact["pdf_page_count"],
        }
    masonry = _source_result(first, "post-6735")
    assert [
        link["label"]
        for link in cast(
            list[JsonObject], cast(JsonObject, masonry["projection"])["document_links"]
        )
    ] == ["نسخه سوم", "نسخه دوم"]
    assert not check_acquisition_health(first, catalog=catalog, root=root)
    (root / "manifest.json").write_bytes(b"{}\n")

    second = acquire_corpus(root, catalog=catalog)

    assert second["summary"]["artifacts_acquired"] == 0
    assert second["summary"]["artifacts_reused"] == 43
    assert {
        cast(str, artifact["catalog_key"]): artifact["initial_transport"]
        for artifact in cast(list[JsonObject], second["artifacts"])
    } == first_transports
    assert all(
        (root / "artifacts" / local_path).stat().st_mtime_ns == modified
        for local_path, modified in first_mtimes.items()
    )
    assert not check_acquisition_health(second, catalog=catalog, root=root)


def test_legacy_reused_receipt_migrates_by_network_attestation_then_reuses(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    root = tmp_path / "acquisition"
    first = acquire_corpus(root, catalog=catalog)
    artifact_mtimes = {
        cast(str, artifact["local_path"]): (
            root / "artifacts" / cast(str, artifact["local_path"])
        )
        .stat()
        .st_mtime_ns
        for artifact in cast(list[JsonObject], catalog["artifacts"])
    }
    legacy = deepcopy(first)
    legacy["schema_version"] = "1.0.0"
    legacy.pop("history")
    for artifact in cast(list[JsonObject], legacy["artifacts"]):
        artifact.pop("initial_transport")
        artifact.update(
            {
                "resolved_url": None,
                "redirect_chain": [],
                "attempts": 0,
                "http_status": None,
                "action": "reused",
            }
        )
    cast(JsonObject, legacy["summary"])["artifacts_acquired"] = 0
    cast(JsonObject, legacy["summary"])["artifacts_reused"] = 43
    (root / "acquisition.json").write_bytes(canonical_bytes(legacy))

    with pytest.raises(AcquisitionError, match="only for unattended migration"):
        validate_acquisition_receipt(legacy, catalog=catalog)

    local_server.requests.clear()
    migrated = acquire_corpus(root, catalog=catalog)

    assert migrated["schema_version"] == "2.0.0"
    assert migrated["summary"]["artifacts_acquired"] == 43
    assert all(
        local_server.requests[_artifact_route(artifact)] == 1
        for artifact in cast(list[JsonObject], catalog["artifacts"])
    )
    assert all(
        (root / "artifacts" / local_path).stat().st_mtime_ns == modified
        for local_path, modified in artifact_mtimes.items()
    )
    initial_transports = {
        cast(str, artifact["catalog_key"]): deepcopy(artifact["initial_transport"])
        for artifact in cast(list[JsonObject], migrated["artifacts"])
    }

    local_server.requests.clear()
    reused = acquire_corpus(root, catalog=catalog)

    assert reused["summary"]["artifacts_reused"] == 43
    assert not any(
        local_server.requests[_artifact_route(artifact)]
        for artifact in cast(list[JsonObject], catalog["artifacts"])
    )
    assert {
        cast(str, artifact["catalog_key"]): artifact["initial_transport"]
        for artifact in cast(list[JsonObject], reused["artifacts"])
    } == initial_transports


def test_redirects_are_explicit_and_remote_names_never_control_storage(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    artifacts = cast(list[JsonObject], catalog["artifacts"])
    approved, rejected = artifacts[:2]
    approved_path = urlsplit(cast(str, approved["download_url"])).path
    rejected_path = urlsplit(cast(str, rejected["download_url"])).path
    redirected_url = f"{local_server.origin}/redirected/approved.pdf"
    local_server.routes[approved_path] = _Route(
        status=302, headers={"Location": redirected_url}
    )
    local_server.routes["/redirected/approved.pdf"] = _Route(
        body=pdf,
        headers={
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="../../escape.pdf"',
        },
    )
    local_server.routes[rejected_path] = _Route(
        status=302, headers={"Location": "http://example.invalid/evil.pdf"}
    )
    approved["remote_filename"] = "nested/../../hostile-server-name.pdf"
    root = tmp_path / "acquisition"
    _preseed_artifacts(
        root, catalog, pdf, skip={approved["catalog_key"], rejected["catalog_key"]}
    )

    receipt = acquire_corpus(root, catalog=catalog)
    approved_result = _artifact_result(receipt, cast(str, approved["catalog_key"]))
    rejected_result = _artifact_result(receipt, cast(str, rejected["catalog_key"]))

    assert approved_result["redirect_chain"] == [approved["download_url"], redirected_url]
    assert approved_result["resolved_url"] == redirected_url
    assert approved_result["state"] == "ready"
    assert rejected_result["state"] == "quarantined"
    assert cast(JsonObject, rejected_result["error"])["code"] == "UNAPPROVED_REDIRECT"
    assert (root / "artifacts" / cast(str, approved["local_path"])).is_file()
    assert not (tmp_path / "escape.pdf").exists()
    assert len(cast(list[JsonObject], receipt["artifacts"])) == 43


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "unexpected",
        "duplicate",
        "relabeled",
        "remapped",
        "userinfo_fragment",
        "invalid_port",
    ],
)
def test_discovery_drift_is_terminal_for_every_link_change(
    mutation: str,
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    source = _catalog_source(catalog, "post-6735")
    links = [
        dict(link) for link in cast(list[JsonObject], source["expected_document_links"])
    ]
    if mutation == "missing":
        links.pop()
    elif mutation == "unexpected":
        links.append({"label": "نسخه چهارم", "href": f"{local_server.origin}/new.pdf"})
    elif mutation == "duplicate":
        links.append(dict(links[0]))
    elif mutation == "relabeled":
        links[0]["label"] = "برچسب تغییر یافته"
    elif mutation == "remapped":
        links[0]["href"] = f"{local_server.origin}/remapped.pdf"
    elif mutation == "userinfo_fragment":
        links[0]["href"] = (
            links[0]["href"].replace("://", "://user:password@", 1) + "#changed"
        )
    else:
        links[0]["href"] = "http://127.0.0.1:not-a-port/remapped.pdf"
    _set_metadata_route(local_server, source, links)
    root = tmp_path / mutation
    _preseed_artifacts(root, catalog, pdf)

    receipt = acquire_corpus(root, catalog=catalog)
    result = _source_result(receipt, "post-6735")

    assert result["state"] == "quarantined"
    assert cast(JsonObject, result["error"])["code"] == "SOURCE_DISCOVERY_DRIFT"
    assert receipt["summary"]["metadata_expected"] == 9
    assert receipt["summary"]["metadata_quarantined"] == 1
    assert receipt["summary"]["artifacts_ready"] == 43


def test_intentional_duplicate_and_mailto_links_are_projected_deterministically(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    root = tmp_path / "acquisition"
    _preseed_artifacts(root, catalog, pdf)

    receipt = acquire_corpus(root, catalog=catalog)
    page_links = cast(
        list[JsonObject],
        cast(JsonObject, _source_result(receipt, "page-5825")["projection"])[
            "document_links"
        ],
    )
    post_links = cast(
        list[JsonObject],
        cast(JsonObject, _source_result(receipt, "post-6022")["projection"])[
            "document_links"
        ],
    )

    assert len(page_links) == 2
    assert page_links[0]["href"] == page_links[1]["href"]
    assert page_links[0]["label"] != page_links[1]["label"]
    assert len(post_links) == 1
    assert post_links[0]["href"].endswith("/historical.pdf")


def test_payload_failures_are_quarantined_without_losing_siblings(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    two_page_pdf = _pdf_bytes(tmp_path, write_pdf, pages=2)
    catalog = _local_catalog(local_server, pdf)
    artifacts = cast(list[JsonObject], catalog["artifacts"])
    html, wrong_hash, wrong_size, wrong_pages = artifacts[:4]
    local_server.routes[_artifact_route(html)] = _Route(
        body=b"<!doctype html><html>not a PDF</html>",
        headers={"Content-Type": "text/html"},
    )
    local_server.routes[_artifact_route(wrong_hash)] = _Route(
        body=pdf + b"\n", headers={"Content-Type": "application/pdf"}
    )
    wrong_size["expected_bytes"] = len(pdf) + 1
    local_server.routes[_artifact_route(wrong_pages)] = _Route(
        body=two_page_pdf, headers={"Content-Type": "application/pdf"}
    )
    wrong_pages["expected_sha256"] = hashlib.sha256(two_page_pdf).hexdigest()
    wrong_pages["expected_bytes"] = len(two_page_pdf)
    root = tmp_path / "acquisition"
    _preseed_artifacts(
        root,
        catalog,
        pdf,
        skip={artifact["catalog_key"] for artifact in artifacts[:4]},
    )

    receipt = acquire_corpus(root, catalog=catalog)
    codes = {
        artifact["catalog_key"]: cast(JsonObject, artifact["error"])["code"]
        for artifact in cast(list[JsonObject], receipt["artifacts"])
        if artifact["state"] == "quarantined"
    }

    assert codes == {
        html["catalog_key"]: "MEDIA_TYPE_MISMATCH",
        wrong_hash["catalog_key"]: "SOURCE_HASH_MISMATCH",
        wrong_size["catalog_key"]: "SOURCE_SIZE_MISMATCH",
        wrong_pages["catalog_key"]: "PDF_PAGE_COUNT_MISMATCH",
    }
    assert receipt["summary"]["artifacts_ready"] == 39
    assert receipt["summary"]["artifacts_quarantined"] == 4
    assert all(
        cast(str, artifact["quarantine_path"]).startswith("quarantine/")
        for artifact in cast(list[JsonObject], receipt["artifacts"])
        if artifact["state"] == "quarantined"
    )
    blockers = check_acquisition_health(receipt, catalog=catalog, root=root)
    assert len(blockers) == 4
    assert {blocker.code for blocker in blockers} == set(codes.values())


def test_successful_rerun_retains_prior_content_addressed_quarantine(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    artifact = cast(list[JsonObject], catalog["artifacts"])[0]
    local_server.routes[_artifact_route(artifact)] = _Route(
        body=pdf + b"changed", headers={"Content-Type": "application/pdf"}
    )
    root = tmp_path / "acquisition"
    _preseed_artifacts(root, catalog, pdf, skip={artifact["catalog_key"]})

    first = acquire_corpus(root, catalog=catalog)
    first_result = _artifact_result(first, cast(str, artifact["catalog_key"]))
    retained_path = root / cast(str, first_result["quarantine_path"])
    assert retained_path.is_file()

    local_server.routes[_artifact_route(artifact)] = _Route(
        body=pdf, headers={"Content-Type": "application/pdf"}
    )
    second = acquire_corpus(root, catalog=catalog)

    assert second["summary"]["artifacts_ready"] == 43
    assert second["summary"]["artifacts_quarantined"] == 0
    assert retained_path.is_file()
    assert cast(list[JsonObject], second["history"]) == [
        {
            "storage_kind": "quarantine",
            "path": cast(str, first_result["quarantine_path"]),
            "sha256": first_result["sha256"],
            "bytes": first_result["bytes"],
            "origins": [
                {
                    "terminal_code": "RETAINED_PRIOR_EVIDENCE",
                    "subject": artifact["catalog_key"],
                    "original_path": None,
                }
            ],
        }
    ]
    assert not check_acquisition_health(second, catalog=catalog, root=root)


def test_recognized_interrupted_writes_are_recovered_into_ordered_history(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    root = tmp_path / "acquisition"
    acquire_corpus(root, catalog=catalog)
    shared = b"shared interrupted payload"
    temporaries = {
        root / ".acquisition.json.receipt_tmp.tmp": shared,
        root / ".manifest.json.manifest_tmp.tmp": shared,
        root / "artifacts" / ".acquire.artifact_tmp": b"artifact temporary",
        root / "metadata" / "raw" / ".acquire.metadata_tmp": b"metadata temporary",
        root
        / "metadata"
        / "projections"
        / ".projection.projection_tmp": b"projection temporary",
    }
    for path, payload in temporaries.items():
        path.write_bytes(payload)

    receipt = acquire_corpus(root, catalog=catalog)

    history = cast(list[JsonObject], receipt["history"])
    assert len(history) == 4
    recovered = {
        cast(str, origin["original_path"]): origin["subject"]
        for entry in history
        for origin in cast(list[JsonObject], entry["origins"])
    }
    assert recovered == {
        ".acquisition.json.receipt_tmp.tmp": "acquisition-receipt",
        ".manifest.json.manifest_tmp.tmp": "inventory-manifest",
        "artifacts/.acquire.artifact_tmp": "artifact-download",
        "metadata/raw/.acquire.metadata_tmp": "metadata-download",
        "metadata/projections/.projection.projection_tmp": "metadata-projection",
    }
    assert all(not path.exists() for path in temporaries)
    for payload in set(temporaries.values()):
        digest = hashlib.sha256(payload).hexdigest()
        assert (root / "quarantine" / digest).read_bytes() == payload

    reordered = deepcopy(receipt)
    cast(list[JsonObject], reordered["history"]).reverse()
    with pytest.raises(AcquisitionError, match="history paths"):
        validate_acquisition_receipt(reordered, catalog=catalog)

    reordered = deepcopy(receipt)
    shared_entry = next(
        entry
        for entry in cast(list[JsonObject], reordered["history"])
        if len(cast(list[JsonObject], entry["origins"])) == 2
    )
    cast(list[JsonObject], shared_entry["origins"]).reverse()
    with pytest.raises(AcquisitionError, match="history origins"):
        validate_acquisition_receipt(reordered, catalog=catalog)


def test_unknown_or_unsafe_interrupted_writes_remain_blockers(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    root = tmp_path / "acquisition"
    acquire_corpus(root, catalog=catalog)
    local_server.requests.clear()
    unknown = root / "quarantine" / ".unknown.tmp"
    unknown.write_bytes(b"unknown")

    with pytest.raises(AcquisitionError, match="unknown interrupted-write"):
        acquire_corpus(root, catalog=catalog)

    unknown.unlink()
    victim = tmp_path / "temporary-victim"
    victim.write_bytes(b"victim")
    (root / "artifacts" / ".acquire.unsafe_tmp").symlink_to(victim)
    with pytest.raises(AcquisitionError, match="unknown interrupted-write"):
        acquire_corpus(root, catalog=catalog)

    assert not local_server.requests


def test_valid_preexisting_target_is_accounted_when_initial_transport_fetch_fails(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    artifact = cast(list[JsonObject], catalog["artifacts"])[0]
    local_server.routes[_artifact_route(artifact)] = _Route(
        body=b"temporarily unavailable",
        status=503,
        headers={"Content-Type": "application/pdf"},
    )
    root = tmp_path / "acquisition"
    _preseed_artifacts(root, catalog, pdf)
    target = root / "artifacts" / cast(str, artifact["local_path"])
    modified = target.stat().st_mtime_ns

    receipt = acquire_corpus(root, catalog=catalog)

    result = _artifact_result(receipt, cast(str, artifact["catalog_key"]))
    assert result["state"] == "quarantined"
    assert result["attempts"] == 2
    assert result["initial_transport"] is None
    assert target.stat().st_mtime_ns == modified
    blockers = check_acquisition_health(receipt, catalog=catalog, root=root)
    assert [blocker.subject for blocker in blockers] == [artifact["local_path"]]


def test_existing_conflict_symlink_and_nonregular_target_are_never_overwritten(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    artifacts = cast(list[JsonObject], catalog["artifacts"])
    conflict, symlinked, fifo = artifacts[:3]
    root = tmp_path / "acquisition"
    _preseed_artifacts(
        root,
        catalog,
        pdf,
        skip={artifact["catalog_key"] for artifact in artifacts[:3]},
    )
    artifact_root = root / "artifacts"
    conflict_path = artifact_root / cast(str, conflict["local_path"])
    conflict_path.write_bytes(b"do not overwrite")
    victim = tmp_path / "victim.pdf"
    victim.write_bytes(b"victim")
    (artifact_root / cast(str, symlinked["local_path"])).symlink_to(victim)
    os.mkfifo(artifact_root / cast(str, fifo["local_path"]))

    receipt = acquire_corpus(root, catalog=catalog)

    assert conflict_path.read_bytes() == b"do not overwrite"
    assert victim.read_bytes() == b"victim"
    assert (
        cast(
            JsonObject,
            _artifact_result(receipt, cast(str, conflict["catalog_key"]))["error"],
        )["code"]
        == "EXISTING_TARGET_CONFLICT"
    )
    for artifact in (symlinked, fifo):
        result = _artifact_result(receipt, cast(str, artifact["catalog_key"]))
        assert cast(JsonObject, result["error"])["code"] == "UNSAFE_EXISTING_TARGET"
    assert receipt["summary"]["artifacts_ready"] == 40

    conflict_path.write_bytes(b"changed after receipt")
    with pytest.raises(AcquisitionError, match="failed existing target differs"):
        check_acquisition_health(receipt, catalog=catalog, root=root)


def test_partial_write_and_timeout_retry_to_terminal_receipts(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    policy = cast(JsonObject, catalog["acquisition_policy"])
    policy["max_attempts"] = 2
    policy["read_timeout_seconds"] = 0.05
    artifacts = cast(list[JsonObject], catalog["artifacts"])
    partial, timeout = artifacts[:2]
    local_server.routes[_artifact_route(partial)] = _Route(
        body=pdf,
        headers={
            "Content-Type": "application/pdf",
            "Content-Length": str(len(pdf) + 20),
        },
        truncate_at=len(pdf) // 2,
    )
    local_server.routes[_artifact_route(timeout)] = _Route(
        body=pdf,
        headers={"Content-Type": "application/pdf"},
        delay_seconds=0.2,
    )
    root = tmp_path / "acquisition"
    _preseed_artifacts(
        root, catalog, pdf, skip={partial["catalog_key"], timeout["catalog_key"]}
    )

    receipt = acquire_corpus(root, catalog=catalog)

    for artifact in (partial, timeout):
        result = _artifact_result(receipt, cast(str, artifact["catalog_key"]))
        assert result["attempts"] == 2
        assert result["state"] == "quarantined"
        assert cast(JsonObject, result["error"])["code"] == "HTTP_RETRY_EXHAUSTED"
        assert local_server.requests[_artifact_route(artifact)] == 2
    assert len(cast(list[JsonObject], receipt["artifacts"])) == 43
    assert not list((root / "artifacts").glob(".acquire.*"))


def test_total_deadline_stops_a_slow_trickle_response(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    policy = cast(JsonObject, catalog["acquisition_policy"])
    policy["read_timeout_seconds"] = 0.1
    policy["total_timeout_seconds"] = 0.2
    slow = cast(list[JsonObject], catalog["artifacts"])[0]
    root = tmp_path / "acquisition"
    acquire_corpus(root, catalog=catalog)
    (root / "artifacts" / cast(str, slow["local_path"])).unlink()
    local_server.routes[_artifact_route(slow)] = _Route(
        body=pdf,
        headers={"Content-Type": "application/pdf"},
        chunk_size=1,
        chunk_delay_seconds=0.03,
    )

    started = time.monotonic()
    receipt = acquire_corpus(root, catalog=catalog)
    elapsed = time.monotonic() - started
    result = _artifact_result(receipt, cast(str, slow["catalog_key"]))

    assert elapsed < 5
    assert result["state"] == "quarantined"
    assert cast(JsonObject, result["error"])["code"] == "TOTAL_TIMEOUT_EXCEEDED"
    assert result["attempts"] == 1
    assert result["http_status"] == 200


def test_receipt_transport_tampering_fails_closed(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    root = tmp_path / "acquisition"
    acquired = acquire_corpus(root, catalog=catalog)
    reused = acquire_corpus(root, catalog=catalog)

    for mutation in (
        "chain_start",
        "resolved",
        "unapproved_hop",
        "redirect_limit",
        "attempts",
        "status",
        "reuse",
    ):
        receipt = deepcopy(reused if mutation == "reuse" else acquired)
        source = cast(list[JsonObject], receipt["metadata_sources"])[0]
        if mutation == "chain_start":
            cast(list[str], source["redirect_chain"])[0] = "http://example.invalid/start"
        elif mutation == "resolved":
            source["resolved_url"] = "http://example.invalid/final"
        elif mutation == "unapproved_hop":
            chain = cast(list[str], source["redirect_chain"])
            chain.insert(1, "http://example.invalid/hop")
        elif mutation == "redirect_limit":
            source["redirect_chain"] = [source["requested_url"]] * 5
        elif mutation == "attempts":
            source["attempts"] = 0
        elif mutation == "status":
            source["http_status"] = 500
        else:
            artifact = cast(list[JsonObject], receipt["artifacts"])[0]
            artifact["attempts"] = 1
            artifact["http_status"] = 200
            artifact["resolved_url"] = artifact["requested_url"]
            artifact["redirect_chain"] = [artifact["requested_url"]]

        with pytest.raises(AcquisitionError):
            validate_acquisition_receipt(receipt, catalog=catalog)


def test_retained_initial_transport_tampering_fails_closed(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    root = tmp_path / "acquisition"
    first = acquire_corpus(root, catalog=catalog)
    receipt = deepcopy(acquire_corpus(root, catalog=catalog))
    artifact = cast(list[JsonObject], receipt["artifacts"])[0]
    assert (
        artifact["initial_transport"]
        == cast(list[JsonObject], first["artifacts"])[0]["initial_transport"]
    )
    for field_name, value in (
        ("resolved_url", "http://example.invalid/final.pdf"),
        ("attempts", 3),
        ("sha256", "0" * 64),
        ("pdf_page_count", 2),
    ):
        tampered = deepcopy(receipt)
        tampered_artifact = cast(list[JsonObject], tampered["artifacts"])[0]
        attestation = cast(JsonObject, tampered_artifact["initial_transport"])
        attestation[field_name] = value
        with pytest.raises(AcquisitionError):
            validate_acquisition_receipt(tampered, catalog=catalog)


def test_public_acquisition_rejects_nonofficial_catalog_origins(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    catalog = _local_catalog(local_server, _pdf_bytes(tmp_path, write_pdf))
    root = tmp_path / "acquisition"
    root.mkdir(mode=0o700)

    with pytest.raises(AcquisitionError, match="official HTTPS INBR origins"):
        _acquire_corpus(root, catalog=catalog)

    assert not local_server.requests


def test_acquisition_rejects_group_or_world_writable_root(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    catalog = _local_catalog(local_server, _pdf_bytes(tmp_path, write_pdf))
    root = tmp_path / "acquisition"
    root.mkdir(mode=0o700)
    root.chmod(0o777)

    with pytest.raises(AcquisitionError, match="group/world writable"):
        _acquire_corpus(
            root,
            catalog=catalog,
            _testing_allowed_origins=_testing_origins(catalog),
        )

    assert not local_server.requests


def test_acquisition_check_detects_snapshot_tampering_and_extra_payloads(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    root = tmp_path / "acquisition"
    _preseed_artifacts(root, catalog, pdf)
    receipt = acquire_corpus(root, catalog=catalog)
    first_source = cast(list[JsonObject], receipt["metadata_sources"])[0]
    raw = root / cast(str, first_source["raw_path"])
    raw.write_bytes(raw.read_bytes() + b" ")

    with pytest.raises(AcquisitionError, match="digest differs"):
        check_acquisition_health(receipt, catalog=catalog, root=root)

    raw.write_bytes(raw.read_bytes()[:-1])
    receipt_file = root / "acquisition.json"
    receipt_file.write_bytes(receipt_file.read_bytes() + b" ")
    with pytest.raises(AcquisitionError, match="stored acquisition receipt differs"):
        check_acquisition_health(receipt, catalog=catalog, root=root)

    receipt_file.write_bytes(canonical_bytes(receipt))
    unexpected = root / "quarantine" / "unexpected"
    unexpected.write_bytes(b"stale")
    with pytest.raises(AcquisitionError, match="storage coverage differs"):
        check_acquisition_health(receipt, catalog=catalog, root=root)

    unexpected.unlink()
    unexpected.mkdir()
    with pytest.raises(AcquisitionError, match="storage coverage differs"):
        check_acquisition_health(receipt, catalog=catalog, root=root)

    unexpected.rmdir()
    os.mkfifo(unexpected)
    with pytest.raises(AcquisitionError, match="storage coverage differs"):
        check_acquisition_health(receipt, catalog=catalog, root=root)


def test_acquisition_check_rejects_correctly_named_unindexed_cas_payload(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    root = tmp_path / "acquisition"
    receipt = acquire_corpus(root, catalog=catalog)
    payload = b"valid content-addressed but unindexed"
    digest = hashlib.sha256(payload).hexdigest()
    (root / "quarantine" / digest).write_bytes(payload)

    with pytest.raises(AcquisitionError, match="storage coverage differs"):
        check_acquisition_health(receipt, catalog=catalog, root=root)


def test_custom_catalog_is_honored_by_every_cli_stage_and_fails_when_omitted(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    cast(list[JsonObject], catalog["families"])[0]["title_en"] = "Custom Definitions"
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(canonical_bytes(catalog))
    root = tmp_path / "acquisition"
    root.mkdir(mode=0o700)
    receipt_path = root / "acquisition.json"
    manifest_path = tmp_path / "manifest.json"

    assert (
        main(
            [
                "acquire",
                "--output-root",
                str(root),
                "--catalog",
                str(catalog_path),
            ],
            _testing_allowed_origins=_testing_origins(catalog),
        )
        == 0
    )
    assert (
        main(
            [
                "acquisition-check",
                str(receipt_path),
                "--root",
                str(root),
                "--catalog",
                str(catalog_path),
            ],
            _testing_allowed_origins=_testing_origins(catalog),
        )
        == 0
    )
    assert (
        main(
            [
                "inventory",
                str(root / "artifacts"),
                "--output",
                str(manifest_path),
                "--catalog",
                str(catalog_path),
            ]
        )
        == 0
    )
    assert main(["validate", str(manifest_path), "--catalog", str(catalog_path)]) == 0
    assert main(["publish-check", str(manifest_path), "--catalog", str(catalog_path)]) == 0
    assert main(["validate", str(manifest_path)]) == 2
    assert main(["acquisition-check", str(receipt_path), "--root", str(root)]) == 2


@pytest.mark.parametrize(
    "unsafe_path", ["../escape.pdf", "/absolute.pdf", "nested/file.pdf", "C:drive.pdf"]
)
def test_catalog_rejects_unsafe_local_storage_paths(unsafe_path: str) -> None:
    catalog = load_catalog()
    cast(list[JsonObject], catalog["artifacts"])[0]["local_path"] = unsafe_path

    with pytest.raises(CatalogError, match=r"local_path|local path"):
        validate_catalog(catalog)


def test_receipt_schema_rejects_nonterminal_and_unknown_fields(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    local_server: _LocalServer,
) -> None:
    pdf = _pdf_bytes(tmp_path, write_pdf)
    catalog = _local_catalog(local_server, pdf)
    root = tmp_path / "acquisition"
    _preseed_artifacts(root, catalog, pdf)
    receipt = acquire_corpus(root, catalog=catalog)
    first = cast(list[JsonObject], receipt["artifacts"])[0]
    first["state"] = "pending"
    first["silently_accepted"] = True

    with pytest.raises(AcquisitionError, match="schema error"):
        validate_acquisition_receipt(receipt, catalog=catalog)


def _local_catalog(server: _LocalServer, pdf: bytes) -> JsonObject:
    catalog = load_catalog()
    policy = cast(JsonObject, catalog["acquisition_policy"])
    policy.update(
        {
            "allowed_origins": [server.origin],
            "max_redirects": 3,
            "max_attempts": 2,
            "connect_timeout_seconds": 1,
            "read_timeout_seconds": 1,
            "total_timeout_seconds": 5,
            "max_metadata_bytes": 1024 * 1024,
            "max_artifact_bytes": 1024 * 1024,
        }
    )
    artifacts = cast(list[JsonObject], catalog["artifacts"])
    for artifact in artifacts:
        artifact["download_url"] = (
            f"{server.origin}/artifacts/{artifact['catalog_key']}.pdf"
        )
        artifact["expected_sha256"] = hashlib.sha256(pdf).hexdigest()
        artifact["expected_bytes"] = len(pdf)
        artifact["expected_pdf_pages"] = 1
        artifact["review_status"] = "accepted"
        artifact["review_flags"] = []
        server.routes[_artifact_route(artifact)] = _Route(
            body=pdf, headers={"Content-Type": "application/pdf"}
        )

    v3 = next(
        artifact
        for artifact in artifacts
        if artifact["catalog_key"] == "guide-masonry-perimeter-walls-v3-1404"
    )
    v2 = next(
        artifact
        for artifact in artifacts
        if artifact["catalog_key"] == "guide-masonry-perimeter-walls-v2-1403"
    )
    for source in cast(list[JsonObject], catalog["metadata_sources"]):
        source["requested_url"] = (
            f"{server.origin}/wp-json/wp/v2/{source['kind']}s/{source['wordpress_id']}"
        )
        links: list[JsonObject] = []
        if source["source_key"] == "page-5825":
            duplicate = f"{server.origin}/protective-appendix"
            links = [
                {"label": "پیوست لازم الاجرا", "href": duplicate},
                {"label": "ضوابط حفاظتی", "href": duplicate},
            ]
        elif source["source_key"] == "post-6022":
            links = [
                {"label": "دانلود پیش نویس", "href": f"{server.origin}/historical.pdf"}
            ]
        elif source["source_key"] == "post-6735":
            links = [
                {"label": "نسخه سوم", "href": v3["download_url"]},
                {"label": "نسخه دوم", "href": v2["download_url"]},
            ]
        _set_metadata_route(server, source, links)
        body = server.routes[urlsplit(cast(str, source["requested_url"])).path].body
        record = cast(JsonObject, json.loads(body))
        projection = project_wordpress_record(record)
        source["expected_document_links"] = projection["document_links"]
        source["expected_semantic_sha256"] = sha256_json(semantic_projection(projection))
    validate_catalog(catalog)
    return catalog


def _set_metadata_route(
    server: _LocalServer, source: JsonObject, links: list[JsonObject]
) -> None:
    anchors = "".join(f'<a href="{link["href"]}">{link["label"]}</a>' for link in links)
    if source["source_key"] == "post-6022":
        anchors = (
            '<a href="mailto:mabhas@inbr.ir">mabhas@inbr.ir</a>'
            + anchors
            + '<a href="mailto:mabhas@inbr.ir">mabhas@inbr.ir</a>'
        )
    record = {
        "id": source["wordpress_id"],
        "status": "publish",
        "date": "2026-01-01T00:00:00",
        "date_gmt": "2025-12-31T20:30:00",
        "modified": "2026-01-02T00:00:00",
        "modified_gmt": "2026-01-01T20:30:00",
        "link": f"{server.origin}/records/{source['wordpress_id']}",
        "title": {"rendered": f"Source {source['source_key']}"},
        "content": {"rendered": f"<p>Official source</p>{anchors}"},
    }
    path = urlsplit(cast(str, source["requested_url"])).path
    server.routes[path] = _Route(
        body=json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json; charset=UTF-8"},
    )


def _preseed_artifacts(
    root: Path, catalog: JsonObject, pdf: bytes, *, skip: set[object] | None = None
) -> None:
    skipped = set() if skip is None else skip
    directory = root / "artifacts"
    directory.mkdir(parents=True)
    root.chmod(0o700)
    directory.chmod(0o700)
    for artifact in cast(list[JsonObject], catalog["artifacts"]):
        if artifact["catalog_key"] not in skipped:
            (directory / cast(str, artifact["local_path"])).write_bytes(pdf)


def _pdf_bytes(
    tmp_path: Path,
    write_pdf: Callable[[Path, int], None],
    *,
    pages: int = 1,
) -> bytes:
    path = tmp_path / f"fixture-{pages}.pdf"
    write_pdf(path, pages)
    return path.read_bytes()


def _artifact_route(artifact: JsonObject) -> str:
    return urlsplit(cast(str, artifact["download_url"])).path


def _artifact_result(receipt: JsonObject, key: str) -> JsonObject:
    return next(
        artifact
        for artifact in cast(list[JsonObject], receipt["artifacts"])
        if artifact["catalog_key"] == key
    )


def _source_result(receipt: JsonObject, key: str) -> JsonObject:
    return next(
        source
        for source in cast(list[JsonObject], receipt["metadata_sources"])
        if source["source_key"] == key
    )


def _catalog_source(catalog: JsonObject, key: str) -> JsonObject:
    return next(
        source
        for source in cast(list[JsonObject], catalog["metadata_sources"])
        if source["source_key"] == key
    )
