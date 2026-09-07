"""Build a deterministic source graph and layered mathematical evidence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from xml.sax.saxutils import escape

from cadgpt_regulations.errors import ManifestError, StructureError, TranscriptionError
from cadgpt_regulations.jsonio import (
    JsonObject,
    canonical_bytes,
    loads_object,
    sha256_json,
    validate_schema,
)
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.storage import (
    InstallStatus,
    StorageError,
    ensure_private_tree,
    install_immutable_bytes,
    read_attested_bytes,
    safe_path,
    validate_output_root,
)
from cadgpt_regulations.transcription import normalize_search_text, validate_transcription

STRUCTURE_SCHEMA_VERSION = "1.0.0"
_LABEL_PATTERN = re.compile(
    r"^\s*([0-9\u06f0-\u06f9\u0660-\u0669]+(?:[-.][0-9\u06f0-\u06f9\u0660-\u0669]+){1,8})(?:\s+|$)"
)
_UCUM = {
    "mm": "mm",
    "cm": "cm",
    "m": "m",
    "m2": "m2",
    "m²": "m2",
    "m3": "m3",
    "m³": "m3",
    "kn": "kN",
    "n": "N",
    "mpa": "MPa",
    "pa": "Pa",
    "kg": "kg",
    "s": "s",
    "hz": "Hz",
    "°c": "Cel",
    "میلی‌متر": "mm",
    "میلی متر": "mm",
    "سانتی‌متر": "cm",
    "سانتی متر": "cm",
    "متر": "m",
    "مترمربع": "m2",
    "متر مربع": "m2",
    "مترمکعب": "m3",
    "متر مکعب": "m3",
    "کیلو‌نیوتن": "kN",
    "کیلو نیوتن": "kN",
    "مگاپاسکال": "MPa",
}


@dataclass(frozen=True)
class StructureRun:
    manifest: JsonObject
    manifest_path: Path
    graphs_created: int
    graphs_reused: int


def build_structure(
    transcription: JsonObject,
    *,
    transcription_root: Path,
    output_root: Path,
) -> StructureRun:
    """Convert every transcribed page into an ordered, source-anchored graph."""
    try:
        validate_output_root(output_root, description="structure output root")
        validate_transcription(transcription, root=transcription_root)
    except (StorageError, TranscriptionError) as exc:
        raise StructureError(str(exc)) from exc

    graph_records: list[JsonObject] = []
    created = 0
    reused = 0
    for raw_document in cast(list[JsonObject], transcription["documents"]):
        graph = _build_document_graph(raw_document, root=transcription_root)
        _validate_graph_schema(graph)
        payload = canonical_bytes(graph)
        digest = hashlib.sha256(payload).hexdigest()
        relative = Path("graphs") / cast(str, graph["source_sha256"]) / f"{digest}.json"
        try:
            ensure_private_tree(output_root, relative.parent.as_posix())
            result = install_immutable_bytes(
                safe_path(output_root, relative.as_posix()), payload
            )
        except StorageError as exc:
            raise StructureError(str(exc)) from exc
        created += result.status is InstallStatus.INSTALLED
        reused += result.status is InstallStatus.REUSED
        graph_records.append(
            {
                "catalog_key": graph["catalog_key"],
                "catalog_order": graph["catalog_order"],
                "source_sha256": graph["source_sha256"],
                "pdf_page_count": graph["pdf_page_count"],
                "path": relative.as_posix(),
                "sha256": digest,
                "bytes": len(payload),
                "counts": graph["counts"],
                "bundles": _install_structural_bundles(
                    graph,
                    transcription_document=raw_document,
                    output_root=output_root,
                    graph_sha256=digest,
                ),
            }
        )

    summary = _manifest_summary(graph_records)
    manifest: JsonObject = {
        "schema_version": STRUCTURE_SCHEMA_VERSION,
        "transcription_sha256": sha256_json(transcription),
        "configuration_sha256": cast(JsonObject, transcription["configuration"])["sha256"],
        "documents": graph_records,
        "summary": summary,
    }
    validate_structure(
        manifest,
        root=output_root,
        transcription=transcription,
        transcription_root=transcription_root,
    )
    install = install_immutable_bytes(
        output_root / "structure.json", canonical_bytes(manifest)
    )
    del install
    return StructureRun(
        manifest=manifest,
        manifest_path=output_root / "structure.json",
        graphs_created=created,
        graphs_reused=reused,
    )


def validate_structure(
    manifest: JsonObject,
    *,
    root: Path,
    transcription: JsonObject,
    transcription_root: Path,
) -> None:
    """Re-attest every graph, anchor, formula crop, and source page."""
    try:
        schema = load_packaged_json("cadgpt_regulations.schemas", "structure.schema.json")
        validate_schema(manifest, schema, description="structure manifest")
        validate_transcription(transcription, root=transcription_root)
    except (ManifestError, StorageError, TranscriptionError) as exc:
        raise StructureError(str(exc)) from exc
    if manifest["transcription_sha256"] != sha256_json(transcription):
        raise StructureError("structure references a different transcription")

    source_documents = cast(list[JsonObject], transcription["documents"])
    references = cast(list[JsonObject], manifest["documents"])
    if len(references) != len(source_documents):
        raise StructureError("structure document count differs from transcription")
    for reference, source_document in zip(references, source_documents, strict=True):
        if reference["catalog_key"] != source_document["catalog_key"]:
            raise StructureError("structure document order differs from transcription")
        try:
            payload, snapshot = read_attested_bytes(
                safe_path(root, cast(str, reference["path"])),
                expected_sha256=cast(str, reference["sha256"]),
                expected_bytes=cast(int, reference["bytes"]),
            )
        except StorageError as exc:
            raise StructureError(str(exc)) from exc
        graph = loads_object(payload.decode("utf-8"), description="source graph")
        _validate_graph_schema(graph)
        if snapshot.sha256 != reference["sha256"]:
            raise StructureError("source graph hash differs from its reference")
        _validate_graph(
            graph,
            source_document=source_document,
            transcription_root=transcription_root,
        )
        source_bundles = cast(list[JsonObject], source_document["bundles"])
        structural_bundles = reference.get("bundles")
        if not isinstance(structural_bundles, list):
            raise StructureError("structure document has no canonical bundles")
        if len(structural_bundles) != len(source_bundles):
            raise StructureError("canonical bundle count differs from transcription")
        for bundle, source_bundle in zip(structural_bundles, source_bundles, strict=True):
            for field in ("sequence", "start_pdf_page", "end_pdf_page", "page_count"):
                if bundle.get(field) != source_bundle.get(field):
                    raise StructureError(f"canonical bundle differs at {field}")
            try:
                payload, snapshot = read_attested_bytes(
                    safe_path(root, cast(str, bundle["path"])),
                    expected_sha256=cast(str, bundle["sha256"]),
                    expected_bytes=cast(int, bundle["bytes"]),
                )
                loaded = loads_object(
                    payload.decode("utf-8"), description="structural bundle"
                )
            except (StorageError, KeyError, TypeError, UnicodeDecodeError) as exc:
                raise StructureError(f"invalid structural bundle: {exc}") from exc
            if (
                loaded.get("catalog_key") != graph["catalog_key"]
                or loaded.get("source_sha256") != graph["source_sha256"]
            ):
                raise StructureError("structural bundle source identity differs")
            try:
                validate_schema(
                    loaded,
                    load_packaged_json(
                        "cadgpt_regulations.schemas", "structural-bundle.schema.json"
                    ),
                    description="structural bundle",
                )
            except ManifestError as exc:
                raise StructureError(str(exc)) from exc
            if loaded.get("graph_sha256") != reference["sha256"]:
                # graph hash is the graph reference digest, not the bundle digest.
                raise StructureError("structural bundle graph identity differs")
            if snapshot.sha256 != bundle["sha256"]:
                raise StructureError("structural bundle hash differs from its reference")
            _validate_structural_bundle_contents(
                loaded,
                graph=graph,
                source_document=source_document,
                source_bundle=source_bundle,
                bundle_reference=bundle,
            )
        if graph["counts"] != reference["counts"]:
            raise StructureError("source graph counts differ from its reference")
    if manifest["summary"] != _manifest_summary(references):
        raise StructureError("structure summary is false")


def _validate_structural_bundle_contents(
    bundle: JsonObject,
    *,
    graph: JsonObject,
    source_document: JsonObject,
    source_bundle: JsonObject,
    bundle_reference: JsonObject,
) -> None:
    start = cast(int, source_bundle["start_pdf_page"])
    end = cast(int, source_bundle["end_pdf_page"])
    pages = cast(list[JsonObject], graph["pages"])
    expected_pages = [
        {
            **page,
            "blocks": [
                node
                for node in cast(list[JsonObject], graph["nodes"])
                if node["pdf_page"] == page["pdf_page"]
            ],
        }
        for page in pages
        if start <= cast(int, page["pdf_page"]) <= end
    ]
    actual_pages = bundle.get("pages")
    if actual_pages != expected_pages:
        raise StructureError("structural bundle pages or blocks differ from graph")
    if bundle.get("sequence") != source_bundle["sequence"]:
        raise StructureError("structural bundle sequence differs from transcription")
    if bundle.get("start_pdf_page") != start or bundle.get("end_pdf_page") != end:
        raise StructureError("structural bundle range differs from transcription")
    if len(expected_pages) != bundle_reference["page_count"]:
        raise StructureError("structural bundle page count is false")
    page_numbers = {cast(int, page["pdf_page"]) for page in expected_pages}
    for collection, id_field in (
        ("formulas", "formula_id"),
        ("tables", "table_id"),
        ("units", "unit_id"),
    ):
        expected = [
            item
            for item in cast(list[JsonObject], graph[collection])
            if cast(int, item["pdf_page"]) in page_numbers
        ]
        if bundle.get(collection) != expected:
            raise StructureError(f"structural bundle {collection} differ from graph")
        ids = [cast(str, item[id_field]) for item in expected]
        if len(ids) != len(set(ids)):
            raise StructureError(f"structural bundle repeats {id_field}")
    expected_edges = [
        edge
        for edge in cast(list[JsonObject], graph["continuation_edges"])
        if start <= cast(int, edge["from_pdf_page"]) <= end
        or start <= cast(int, edge["to_pdf_page"]) <= end
    ]
    if bundle.get("continuation_edges") != expected_edges:
        raise StructureError("structural bundle continuation edges differ from graph")
    if source_document.get("catalog_key") != bundle.get("catalog_key"):
        raise StructureError("structural bundle catalog identity differs")


def _build_document_graph(document: JsonObject, *, root: Path) -> JsonObject:
    nodes: list[JsonObject] = []
    formulas: list[JsonObject] = []
    units: list[JsonObject] = []
    tables: list[JsonObject] = []
    pages: list[JsonObject] = []
    parent_stack: dict[int, str] = {}
    source_order = 0

    for page in cast(list[JsonObject], document["pages"]):
        page_nodes: list[str] = []
        page_formulas: list[str] = []
        page_units: list[str] = []
        page_tables: list[str] = []
        evidence: JsonObject | None = None
        if page["package_path"] is not None:
            package = Path(cast(str, page["package_path"]))
            evidence = _load_json(root, package / "evidence.json", "page evidence")
            lines = _page_lines(evidence, package=package, root=root)
            alternate_lines = _alternate_page_lines(evidence, root=root)
            aligned_alternates = _align_alternate_lines(lines, alternate_lines)
            for index, line in enumerate(lines):
                raw_text = cast(str, line["raw_text"])
                if not raw_text.strip():
                    continue
                source_order += 1
                label_match = _LABEL_PATTERN.match(raw_text)
                label = label_match.group(1) if label_match else None
                depth = len(re.split(r"[-.]", label)) if label else None
                kind = _node_kind(depth)
                parent_id = _node_parent(parent_stack, depth)
                node_id = (
                    f"{page['page_id']}:structure:{source_order:06d}:"
                    f"{cast(str, line['source_kind'])}"
                )
                node: JsonObject = {
                    "node_id": node_id,
                    "kind": kind,
                    "source_order": source_order,
                    "pdf_page": page["pdf_page"],
                    "parent_id": parent_id,
                    "children_ids": [],
                    "printed_label": label,
                    "source_kind": line["source_kind"],
                    "source_span_ids": [line["span_id"]],
                    "raw_text": raw_text,
                    "normalized_text": normalize_search_text(raw_text)[0],
                    "bbox": line["bbox"],
                    "state": "needs_review" if page["state"] != "ready" else "ready",
                }
                alternate = aligned_alternates[index]
                if alternate is not None:
                    node["alternate_source_span_ids"] = [alternate["span_id"]]
                    node["alternate_raw_text"] = alternate["raw_text"]
                nodes.append(node)
                page_nodes.append(node_id)
                if depth is not None:
                    parent_stack[depth] = node_id
                    for stale_depth in [key for key in parent_stack if key > depth]:
                        del parent_stack[stale_depth]

            semantic = cast(JsonObject, evidence["semantic_evidence"])
            crop_artifacts = {
                Path(cast(str, artifact["path"])).name: artifact
                for artifact in cast(list[JsonObject], evidence["artifacts"])
                if artifact["role"] == "formula_crop"
            }
            for candidate in cast(list[JsonObject], semantic["symbols"]):
                kind = candidate["kind"]
                if kind == "equation":
                    record = _formula_record(candidate, crop_artifacts=crop_artifacts)
                    formulas.append(record)
                    page_formulas.append(cast(str, record["formula_id"]))
                elif kind == "unit_mention":
                    record = _unit_record(candidate, page_id=cast(str, page["page_id"]))
                    units.append(record)
                    page_units.append(cast(str, record["unit_id"]))
            for index, candidate in enumerate(cast(list[JsonObject], semantic["tables"])):
                table_id = f"{page['page_id']}:table:{index:04d}"
                record = {
                    "table_id": table_id,
                    "pdf_page": page["pdf_page"],
                    "source_span_ids": [line["span_id"] for line in lines],
                    "reasons": candidate["reasons"],
                    "rows": [],
                    "state": "needs_review",
                    "diagnostics": ["TABLE_GRID_NOT_DETERMINISTICALLY_RECOVERED"],
                }
                tables.append(record)
                page_tables.append(table_id)

        pages.append(
            {
                "page_id": page["page_id"],
                "pdf_page": page["pdf_page"],
                "printed_page_label": page["printed_page_label"],
                "state": page["state"],
                "reason_codes": page["reason_codes"],
                "source_artifacts": _page_artifact_refs(evidence, root=root),
                "node_ids": page_nodes,
                "formula_ids": page_formulas,
                "unit_ids": page_units,
                "table_ids": page_tables,
            }
        )

    by_id = {cast(str, node["node_id"]): node for node in nodes}
    for node in nodes:
        parent_id = node["parent_id"]
        if parent_id is not None:
            cast(list[str], by_id[cast(str, parent_id)]["children_ids"]).append(
                cast(str, node["node_id"])
            )
    continuations = _document_continuations(document, root=root)
    graph: JsonObject = {
        "schema_version": STRUCTURE_SCHEMA_VERSION,
        "catalog_key": document["catalog_key"],
        "catalog_order": document["catalog_order"],
        "source_sha256": document["source_sha256"],
        "pdf_page_count": document["pdf_page_count"],
        "pages": pages,
        "nodes": nodes,
        "tables": tables,
        "formulas": formulas,
        "units": units,
        "continuation_edges": continuations,
        "counts": {
            "pages": len(pages),
            "nodes": len(nodes),
            "tables": len(tables),
            "formulas": len(formulas),
            "units": len(units),
            "continuation_edges": len(continuations),
            "needs_review": sum(page["state"] != "ready" for page in pages)
            + len(tables)
            + len(formulas),
        },
    }
    return graph


def _install_structural_bundles(
    graph: JsonObject,
    *,
    transcription_document: JsonObject,
    output_root: Path,
    graph_sha256: str,
) -> list[JsonObject]:
    """Persist bounded canonical Persian page-block bundles for model consumers."""
    pages = cast(list[JsonObject], graph["pages"])
    nodes = cast(list[JsonObject], graph["nodes"])
    by_page: dict[int, list[JsonObject]] = {}
    for node in nodes:
        by_page.setdefault(cast(int, node["pdf_page"]), []).append(node)
    result: list[JsonObject] = []
    formulas = cast(list[JsonObject], graph["formulas"])
    tables = cast(list[JsonObject], graph["tables"])
    units = cast(list[JsonObject], graph["units"])
    for reference in cast(list[JsonObject], transcription_document["bundles"]):
        sequence = cast(int, reference["sequence"])
        start = cast(int, reference["start_pdf_page"])
        end = cast(int, reference["end_pdf_page"])
        chunk = [page for page in pages if start <= cast(int, page["pdf_page"]) <= end]
        page_numbers = [cast(int, page["pdf_page"]) for page in chunk]
        payload_object: JsonObject = {
            "schema_version": "1.0.0",
            "catalog_key": graph["catalog_key"],
            "source_sha256": graph["source_sha256"],
            "graph_sha256": graph_sha256,
            "sequence": sequence,
            "start_pdf_page": page_numbers[0],
            "end_pdf_page": page_numbers[-1],
            "continuation_edges": [
                edge
                for edge in cast(list[JsonObject], graph["continuation_edges"])
                if start <= cast(int, edge["from_pdf_page"]) <= end
                or start <= cast(int, edge["to_pdf_page"]) <= end
            ],
            "pages": [
                {
                    **page,
                    "blocks": by_page.get(cast(int, page["pdf_page"]), []),
                }
                for page in chunk
            ],
            "formulas": [
                item for item in formulas if cast(int, item["pdf_page"]) in page_numbers
            ],
            "tables": [
                item for item in tables if cast(int, item["pdf_page"]) in page_numbers
            ],
            "units": [
                item for item in units if cast(int, item["pdf_page"]) in page_numbers
            ],
        }
        payload = canonical_bytes(payload_object)
        digest = hashlib.sha256(payload).hexdigest()
        relative = (
            Path("bundles")
            / cast(str, graph["source_sha256"])
            / f"{sequence:06d}-{digest}.json"
        )
        ensure_private_tree(output_root, relative.parent.as_posix())
        install_immutable_bytes(safe_path(output_root, relative.as_posix()), payload)
        result.append(
            {
                "sequence": sequence,
                "start_pdf_page": start,
                "end_pdf_page": end,
                "page_count": len(chunk),
                "path": relative.as_posix(),
                "sha256": digest,
                "bytes": len(payload),
            }
        )
    return result


def _page_lines(evidence: JsonObject, *, package: Path, root: Path) -> list[JsonObject]:
    probe = cast(JsonObject, evidence["probe"])
    probe_package = Path(cast(str, probe["package_path"]))
    native = _load_json(root, probe_package / "native.json", "native layout")
    native_lines = [
        {**line, "source_kind": "native"}
        for line in cast(list[JsonObject], native["lines"])
    ]
    route = cast(str, probe["route"])
    if route not in {"ocr", "native_plus_ocr"}:
        return native_lines
    ocr = _load_json(root, package / "ocr.json", "OCR layout")
    ocr_lines = [
        {**line, "source_kind": "ocr"} for line in cast(list[JsonObject], ocr["lines"])
    ]
    if route == "ocr":
        return ocr_lines
    # Native+OCR pages expose one canonical stream to downstream models. Native
    # evidence remains persisted in the page package for audit, while OCR is
    # selected here because the probe marked the native layer incomplete.
    return ocr_lines


def _all_page_lines(evidence: JsonObject, *, package: Path, root: Path) -> list[JsonObject]:
    """Return canonical plus alternate evidence spans for anchor validation."""
    canonical = _page_lines(evidence, package=package, root=root)
    route = cast(str, cast(JsonObject, evidence["probe"])["route"])
    if route != "native_plus_ocr":
        return canonical
    probe_package = Path(cast(str, cast(JsonObject, evidence["probe"])["package_path"]))
    native = _load_json(root, probe_package / "native.json", "native layout")
    native_lines = [
        {**line, "source_kind": "native"}
        for line in cast(list[JsonObject], native["lines"])
    ]
    return [*canonical, *native_lines]


def _alternate_page_lines(evidence: JsonObject, *, root: Path) -> list[JsonObject] | None:
    if cast(str, cast(JsonObject, evidence["probe"])["route"]) != "native_plus_ocr":
        return None
    probe_package = Path(cast(str, cast(JsonObject, evidence["probe"])["package_path"]))
    native = _load_json(root, probe_package / "native.json", "native layout")
    return [
        {**line, "source_kind": "native"}
        for line in cast(list[JsonObject], native["lines"])
    ]


def _align_alternate_lines(
    canonical_lines: list[JsonObject],
    alternate_lines: list[JsonObject] | None,
) -> list[JsonObject | None]:
    """Link only exact normalized-text matches, never positional guesses."""
    if alternate_lines is None:
        return [None for _ in canonical_lines]
    result: list[JsonObject | None] = []
    cursor = 0
    for canonical in canonical_lines:
        target = normalize_search_text(cast(str, canonical["raw_text"]))[0]
        match_index: int | None = None
        for index in range(cursor, len(alternate_lines)):
            candidate = alternate_lines[index]
            if normalize_search_text(cast(str, candidate["raw_text"]))[0] == target:
                match_index = index
                break
        if match_index is None:
            result.append(None)
            continue
        result.append(alternate_lines[match_index])
        cursor = match_index + 1
    return result


def _page_artifact_refs(
    evidence: JsonObject | None, *, root: Path | None = None
) -> list[JsonObject]:
    if evidence is None:
        return []
    refs = [
        {
            "role": artifact["role"],
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "bytes": artifact["bytes"],
            "media_type": artifact["media_type"],
        }
        for artifact in cast(list[JsonObject], evidence["artifacts"])
    ]
    if root is not None:
        probe_package = Path(cast(str, cast(JsonObject, evidence["probe"])["package_path"]))
        page_package = _load_json(root, probe_package / "page.json", "page package")
        existing_paths = {cast(str, ref["path"]) for ref in refs}
        for artifact in cast(list[JsonObject], page_package["artifacts"]):
            if artifact["role"] not in {"native_layout", "source_render"}:
                continue
            path = cast(str, artifact["path"])
            if path in existing_paths:
                continue
            refs.append(
                {
                    "role": artifact["role"],
                    "path": path,
                    "sha256": artifact["sha256"],
                    "bytes": artifact["bytes"],
                    "media_type": artifact["media_type"],
                }
            )
    return refs


def _formula_record(
    candidate: JsonObject, *, crop_artifacts: dict[str, JsonObject]
) -> JsonObject:
    crop_file = cast(str, candidate["crop_file"])
    artifact = crop_artifacts.get(Path(crop_file).name)
    if artifact is None:
        raise StructureError(f"formula crop is missing: {candidate['candidate_id']}")
    raw = cast(str, candidate["raw_text"])
    return {
        "formula_id": candidate["candidate_id"],
        "pdf_page": _page_from_span(cast(str, candidate["span_id"])),
        "source_kind": candidate["source_kind"],
        "source_span_ids": [candidate["span_id"]],
        "bbox": candidate["bbox"],
        "crop": {
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "bytes": artifact["bytes"],
        },
        "raw_transcription": raw,
        "unicode": raw,
        "latex": None,
        "presentation_mathml": (
            '<math xmlns="http://www.w3.org/1998/Math/MathML"><mtext>'
            + escape(raw)
            + "</mtext></math>"
        ),
        "content_mathml": None,
        "parse_status": "needs_review",
        "diagnostics": ["FORMULA_SEMANTIC_PARSE_DEFERRED"],
        "unresolved_glyphs": [],
    }


def _unit_record(candidate: JsonObject, *, page_id: str) -> JsonObject:
    printed = cast(str, candidate["raw_text"])
    canonical = printed.casefold().replace("\u200c", " ").strip()
    compact = canonical.replace(" ", "")
    ucum = _UCUM.get(canonical) or _UCUM.get(compact)
    return {
        "unit_id": candidate.get("candidate_id")
        or f"{page_id}:unit:{hashlib.sha256(canonical.encode()).hexdigest()[:12]}",
        "pdf_page": _page_from_span(cast(str, candidate["span_id"])),
        "source_kind": candidate["source_kind"],
        "source_span_ids": [candidate["span_id"]],
        "bbox": candidate["bbox"],
        "printed": printed,
        "ucum_code": ucum,
        "mapping_status": "mapped" if ucum is not None else "unknown",
    }


def _node_kind(depth: int | None) -> str:
    if depth is None:
        return "paragraph"
    if depth <= 2:
        return "section"
    if depth == 3:
        return "clause"
    return "subclause"


def _node_parent(stack: dict[int, str], depth: int | None) -> str | None:
    if depth is None:
        return stack[max(stack)] if stack else None
    candidates = [key for key in stack if key < depth]
    return stack[max(candidates)] if candidates else None


def _document_continuations(document: JsonObject, *, root: Path) -> list[JsonObject]:
    seen: set[tuple[str, str, str]] = set()
    result: list[JsonObject] = []
    for reference in cast(list[JsonObject], document["bundles"]):
        bundle = _load_json(root, Path(cast(str, reference["path"])), "bundle")
        for edge in cast(list[JsonObject], bundle["continuation_edges"]):
            identity = (
                cast(str, edge["from_page_id"]),
                cast(str, edge["to_page_id"]),
                cast(str, edge["reason"]),
            )
            if identity not in seen:
                seen.add(identity)
                result.append(edge)
    result.sort(key=lambda edge: (edge["from_pdf_page"], edge["to_pdf_page"]))
    return result


def _validate_graph_schema(graph: JsonObject) -> None:
    try:
        schema = load_packaged_json(
            "cadgpt_regulations.schemas", "source-graph.schema.json"
        )
        validate_schema(graph, schema, description="source graph")
    except ManifestError as exc:
        raise StructureError(str(exc)) from exc


def _validate_graph(
    graph: JsonObject,
    *,
    source_document: JsonObject,
    transcription_root: Path,
) -> None:
    for field in ("catalog_key", "catalog_order", "source_sha256", "pdf_page_count"):
        if graph[field] != source_document[field]:
            raise StructureError(f"source graph differs from transcription at {field}")
    expected_pages = [
        (cast(str, page["page_id"]), cast(int, page["pdf_page"]))
        for page in cast(list[JsonObject], source_document["pages"])
    ]
    pages = cast(list[JsonObject], graph["pages"])
    if [
        (cast(str, page["page_id"]), cast(int, page["pdf_page"])) for page in pages
    ] != expected_pages:
        raise StructureError("source graph page coverage differs from transcription")

    allowed_by_page: dict[int, set[str]] = {}
    canonical_spans_by_page: dict[int, set[str]] = {}
    canonical_lines_by_page: dict[int, dict[str, JsonObject]] = {}
    alternate_lines_by_page: dict[int, dict[str, JsonObject]] = {}
    symbols_by_page: dict[int, dict[str, JsonObject]] = {}
    tables_by_page: dict[int, list[JsonObject]] = {}
    graph_pages_by_id = {
        cast(str, page["page_id"]): page for page in cast(list[JsonObject], graph["pages"])
    }
    for source_page in cast(list[JsonObject], source_document["pages"]):
        page_number = cast(int, source_page["pdf_page"])
        graph_page = graph_pages_by_id.get(cast(str, source_page["page_id"]))
        if graph_page is None:
            raise StructureError("source graph is missing a transcription page")
        if source_page["package_path"] is None:
            allowed_by_page[page_number] = set()
            canonical_lines_by_page[page_number] = {}
            alternate_lines_by_page[page_number] = {}
            symbols_by_page[page_number] = {}
            tables_by_page[page_number] = []
            if graph_page.get("source_artifacts") != []:
                raise StructureError("source graph page artifacts differ from evidence")
            continue
        package = Path(cast(str, source_page["package_path"]))
        evidence = _load_json(
            transcription_root, package / "evidence.json", "page evidence"
        )
        semantic = cast(JsonObject, evidence["semantic_evidence"])
        symbols_by_page[page_number] = {
            cast(str, symbol["candidate_id"]): symbol
            for symbol in cast(list[JsonObject], semantic["symbols"])
        }
        tables_by_page[page_number] = cast(list[JsonObject], semantic["tables"])
        expected_artifacts = _page_artifact_refs(evidence, root=transcription_root)
        if graph_page.get("source_artifacts") != expected_artifacts:
            raise StructureError("source graph page artifacts differ from evidence")
        for artifact in expected_artifacts:
            read_attested_bytes(
                safe_path(transcription_root, cast(str, artifact["path"])),
                expected_sha256=cast(str, artifact["sha256"]),
                expected_bytes=cast(int, artifact["bytes"]),
            )
        canonical_lines = _page_lines(evidence, package=package, root=transcription_root)
        canonical_lines_by_page[page_number] = {
            cast(str, line["span_id"]): line for line in canonical_lines
        }
        alternate_lines = _alternate_page_lines(evidence, root=transcription_root)
        alternate_lines_by_page[page_number] = (
            {}
            if alternate_lines is None
            else {cast(str, line["span_id"]): line for line in alternate_lines}
        )
        allowed_by_page[page_number] = {
            cast(str, line["span_id"])
            for line in _all_page_lines(evidence, package=package, root=transcription_root)
        }
        canonical_spans_by_page[page_number] = {
            cast(str, line["span_id"])
            for line in canonical_lines
            if cast(str, line["raw_text"]).strip()
        }

    node_ids = [
        cast(str, node["node_id"]) for node in cast(list[JsonObject], graph["nodes"])
    ]
    if len(node_ids) != len(set(node_ids)):
        raise StructureError("source graph repeats a node ID")
    node_set = set(node_ids)
    page_map = {cast(str, page["page_id"]): page for page in pages}
    page_node_membership: dict[str, set[str]] = {
        cast(str, page["page_id"]): set(cast(list[str], page["node_ids"])) for page in pages
    }
    if len(page_map) != len(pages):
        raise StructureError("source graph repeats a page ID")
    if any(
        len(cast(list[str], page["node_ids"]))
        != len(page_node_membership[cast(str, page["page_id"])])
        for page in pages
    ):
        raise StructureError("source graph repeats a page node ID")
    if any(
        node_id not in node_set
        for members in page_node_membership.values()
        for node_id in members
    ):
        raise StructureError("source graph page references an unknown node")
    nodes_by_page: dict[int, list[JsonObject]] = {}
    for node in cast(list[JsonObject], graph["nodes"]):
        nodes_by_page.setdefault(cast(int, node["pdf_page"]), []).append(node)
    for page in pages:
        page_number = cast(int, page["pdf_page"])
        expected_ids = [
            cast(str, node["node_id"]) for node in nodes_by_page.get(page_number, [])
        ]
        if cast(list[str], page["node_ids"]) != expected_ids:
            raise StructureError("source graph page node order is false")
    seen_spans: set[str] = set()
    membership_count: dict[str, int] = {}
    for node in cast(list[JsonObject], graph["nodes"]):
        parent = node["parent_id"]
        if parent is not None and parent not in node_set:
            raise StructureError("source graph has an orphan node")
        for child in cast(list[str], node["children_ids"]):
            if child not in node_set:
                raise StructureError("source graph has an unknown child node")
            child_record = next(
                item
                for item in cast(list[JsonObject], graph["nodes"])
                if item["node_id"] == child
            )
            if child_record.get("parent_id") != node["node_id"]:
                raise StructureError("source graph parent/child links are not reciprocal")
        page_id = next(
            (
                pid
                for pid, members in page_node_membership.items()
                if cast(str, node["node_id"]) in members
            ),
            None,
        )
        if page_id is None or cast(int, page_map[page_id]["pdf_page"]) != cast(
            int, node["pdf_page"]
        ):
            raise StructureError("source graph node is not a member of its page")
        membership_count[cast(str, node["node_id"])] = sum(
            cast(str, node["node_id"]) in members
            for members in page_node_membership.values()
        )
        if membership_count[cast(str, node["node_id"])] != 1:
            raise StructureError("source graph node belongs to multiple pages")
        for span in cast(list[str], node["source_span_ids"]):
            if span in seen_spans:
                raise StructureError("source graph assigns a source span more than once")
            seen_spans.add(span)
        _validate_anchors(node, allowed_by_page=allowed_by_page)
        _validate_node_source(
            node,
            canonical_lines_by_page=canonical_lines_by_page,
        )
        alternate_spans = node.get("alternate_source_span_ids", [])
        if not isinstance(alternate_spans, list) or any(
            not isinstance(span, str)
            or span not in allowed_by_page.get(cast(int, node["pdf_page"]), set())
            for span in alternate_spans
        ):
            raise StructureError("source graph contains an invalid alternate span anchor")
        if alternate_spans:
            _validate_node_alternate_source(
                node,
                alternate_lines_by_page=alternate_lines_by_page,
            )
    if seen_spans != set().union(*canonical_spans_by_page.values()):
        raise StructureError("source graph does not cover every canonical source span")
    for page_number, lines in canonical_lines_by_page.items():
        expected_spans = [
            cast(str, line["span_id"])
            for line in lines.values()
            if cast(str, line["raw_text"]).strip()
        ]
        actual_spans = [
            span
            for node in nodes_by_page.get(page_number, [])
            for span in cast(list[str], node["source_span_ids"])
        ]
        if actual_spans != expected_spans:
            raise StructureError("source graph source order differs from evidence")
    for node in cast(list[JsonObject], graph["nodes"]):
        parent = node.get("parent_id")
        if parent is not None and cast(str, node["node_id"]) not in cast(
            list[str],
            next(
                item
                for item in cast(list[JsonObject], graph["nodes"])
                if item["node_id"] == parent
            )["children_ids"],
        ):
            raise StructureError("source graph parent link is not reciprocal")
    _validate_node_order_and_cycles(graph)
    _validate_page_record_lists(graph)
    _validate_continuations(graph)
    for collection in ("tables", "formulas", "units"):
        ids: set[str] = set()
        for record in cast(list[JsonObject], graph[collection]):
            id_field = {
                "tables": "table_id",
                "formulas": "formula_id",
                "units": "unit_id",
            }[collection]
            record_id = cast(str, record[id_field])
            if record_id in ids:
                raise StructureError(f"source graph repeats {id_field}")
            ids.add(record_id)
            _validate_anchors(record, allowed_by_page=allowed_by_page)
            _validate_semantic_record(
                record,
                collection=collection,
                graph_pages=pages,
                symbols_by_page=symbols_by_page,
                tables_by_page=tables_by_page,
                canonical_lines_by_page=canonical_lines_by_page,
            )
    for formula in cast(list[JsonObject], graph["formulas"]):
        crop = cast(JsonObject, formula["crop"])
        read_attested_bytes(
            safe_path(transcription_root, cast(str, crop["path"])),
            expected_sha256=cast(str, crop["sha256"]),
            expected_bytes=cast(int, crop["bytes"]),
        )
    if graph["counts"] != _graph_counts(graph):
        raise StructureError("source graph counts are false")


def _validate_node_source(
    node: JsonObject,
    *,
    canonical_lines_by_page: dict[int, dict[str, JsonObject]],
) -> None:
    spans = cast(list[str], node["source_span_ids"])
    if len(spans) != 1:
        return
    line = canonical_lines_by_page.get(cast(int, node["pdf_page"]), {}).get(spans[0])
    if line is None:
        raise StructureError("source graph node span is not canonical evidence")
    if (
        node["source_kind"] != line["source_kind"]
        or node["raw_text"] != line["raw_text"]
        or node["bbox"] != line["bbox"]
        or node["normalized_text"] != normalize_search_text(cast(str, line["raw_text"]))[0]
    ):
        raise StructureError("source graph node content differs from evidence")


def _validate_node_alternate_source(
    node: JsonObject,
    *,
    alternate_lines_by_page: dict[int, dict[str, JsonObject]],
) -> None:
    spans = cast(list[str], node["alternate_source_span_ids"])
    if len(spans) != 1:
        return
    line = alternate_lines_by_page.get(cast(int, node["pdf_page"]), {}).get(spans[0])
    if line is None or node.get("alternate_raw_text") != line["raw_text"]:
        raise StructureError("source graph alternate content differs from evidence")


def _validate_semantic_record(
    record: JsonObject,
    *,
    collection: str,
    graph_pages: list[JsonObject],
    symbols_by_page: dict[int, dict[str, JsonObject]],
    tables_by_page: dict[int, list[JsonObject]],
    canonical_lines_by_page: dict[int, dict[str, JsonObject]],
) -> None:
    page_number = cast(int, record["pdf_page"])
    if collection in {"formulas", "units"}:
        id_field = "formula_id" if collection == "formulas" else "unit_id"
        candidate = symbols_by_page.get(page_number, {}).get(cast(str, record[id_field]))
        expected_kind = "equation" if collection == "formulas" else "unit_mention"
        if candidate is None or candidate.get("kind") != expected_kind:
            raise StructureError("source graph semantic candidate differs from evidence")
        expected = {
            "source_kind": candidate["source_kind"],
            "source_span_ids": [candidate["span_id"]],
            "bbox": candidate["bbox"],
        }
        if collection == "formulas":
            expected["raw_transcription"] = candidate["raw_text"]
        else:
            expected["printed"] = candidate["raw_text"]
        if any(record.get(field) != value for field, value in expected.items()):
            raise StructureError("source graph semantic content differs from evidence")
        return

    page_id = next(
        (
            cast(str, page["page_id"])
            for page in graph_pages
            if cast(int, page["pdf_page"]) == page_number
        ),
        None,
    )
    if page_id is None:
        raise StructureError("source graph table has an unknown page")
    table_ids = next(
        cast(list[str], page["table_ids"])
        for page in graph_pages
        if page["page_id"] == page_id
    )
    table_id = cast(str, record["table_id"])
    try:
        index = table_ids.index(table_id)
    except ValueError as exc:
        raise StructureError("source graph table is not a page member") from exc
    candidates = tables_by_page.get(page_number, [])
    if index >= len(candidates):
        raise StructureError("source graph table candidate differs from evidence")
    candidate = candidates[index]
    expected_spans = list(canonical_lines_by_page.get(page_number, {}))
    if (
        record.get("reasons") != candidate.get("reasons")
        or record.get("source_span_ids") != expected_spans
    ):
        raise StructureError("source graph table content differs from evidence")


def _validate_anchors(record: JsonObject, *, allowed_by_page: dict[int, set[str]]) -> None:
    page = cast(int, record["pdf_page"])
    anchors = cast(list[str], record["source_span_ids"])
    if not anchors or any(
        anchor not in allowed_by_page.get(page, set()) for anchor in anchors
    ):
        raise StructureError("source graph contains an unknown span anchor")


def _validate_node_order_and_cycles(graph: JsonObject) -> None:
    nodes = cast(list[JsonObject], graph["nodes"])
    orders = [cast(int, node["source_order"]) for node in nodes]
    if orders != sorted(orders) or orders != list(range(1, len(nodes) + 1)):
        raise StructureError("source graph node order is false")
    by_id = {cast(str, node["node_id"]): node for node in nodes}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise StructureError("source graph parent links contain a cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        parent = by_id[node_id].get("parent_id")
        if parent is not None:
            visit(cast(str, parent))
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in by_id:
        visit(node_id)


def _validate_page_record_lists(graph: JsonObject) -> None:
    pages = cast(list[JsonObject], graph["pages"])
    by_id = {cast(str, page["page_id"]): page for page in pages}
    collections = (("formulas", "formula_id"), ("tables", "table_id"), ("units", "unit_id"))
    for collection, id_field in collections:
        records = cast(list[JsonObject], graph[collection])
        by_page: dict[int, set[str]] = {}
        for record in records:
            by_page.setdefault(cast(int, record["pdf_page"]), set()).add(
                cast(str, record[id_field])
            )
        for page in pages:
            page_ids = set(cast(list[str], page[f"{collection[:-1]}_ids"]))
            if page_ids != by_page.get(cast(int, page["pdf_page"]), set()):
                raise StructureError(f"source graph {collection} page membership is false")
            if cast(str, page["page_id"]) not in by_id:
                raise StructureError("source graph has an unknown page identity")


def _validate_continuations(graph: JsonObject) -> None:
    pages = cast(list[JsonObject], graph["pages"])
    by_id = {cast(str, page["page_id"]): page for page in pages}
    for edge in cast(list[JsonObject], graph["continuation_edges"]):
        from_id = cast(str, edge["from_page_id"])
        to_id = cast(str, edge["to_page_id"])
        if from_id not in by_id or to_id not in by_id:
            raise StructureError("source graph continuation has an unknown page")
        if by_id[from_id]["pdf_page"] != edge["from_pdf_page"]:
            raise StructureError("source graph continuation source page is false")
        if by_id[to_id]["pdf_page"] != edge["to_pdf_page"]:
            raise StructureError("source graph continuation target page is false")


def _graph_counts(graph: JsonObject) -> JsonObject:
    pages = cast(list[JsonObject], graph["pages"])
    return {
        "pages": len(pages),
        "nodes": len(cast(list[JsonObject], graph["nodes"])),
        "tables": len(cast(list[JsonObject], graph["tables"])),
        "formulas": len(cast(list[JsonObject], graph["formulas"])),
        "units": len(cast(list[JsonObject], graph["units"])),
        "continuation_edges": len(cast(list[JsonObject], graph["continuation_edges"])),
        "needs_review": sum(page["state"] != "ready" for page in pages)
        + len(cast(list[JsonObject], graph["tables"]))
        + len(cast(list[JsonObject], graph["formulas"])),
    }


def _manifest_summary(references: list[JsonObject]) -> JsonObject:
    return {
        "documents": len(references),
        "pages": sum(cast(int, item["counts"]["pages"]) for item in references),
        "nodes": sum(cast(int, item["counts"]["nodes"]) for item in references),
        "tables": sum(cast(int, item["counts"]["tables"]) for item in references),
        "formulas": sum(cast(int, item["counts"]["formulas"]) for item in references),
        "units": sum(cast(int, item["counts"]["units"]) for item in references),
        "continuation_edges": sum(
            cast(int, item["counts"]["continuation_edges"]) for item in references
        ),
        "needs_review": sum(
            cast(int, item["counts"]["needs_review"]) for item in references
        ),
    }


def _load_json(root: Path, relative: Path, description: str) -> JsonObject:
    try:
        payload, _ = read_attested_bytes(safe_path(root, relative.as_posix()))
    except StorageError as exc:
        raise StructureError(str(exc)) from exc
    return loads_object(payload.decode("utf-8"), description=description)


def _page_from_span(span_id: str) -> int:
    match = re.search(r":page:([0-9]{6}):", span_id)
    if match is None:
        raise StructureError(f"span has no page identity: {span_id}")
    return int(match.group(1))
