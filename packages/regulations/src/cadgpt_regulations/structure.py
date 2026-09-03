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
from cadgpt_regulations.transcription import validate_transcription

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
        if graph["counts"] != reference["counts"]:
            raise StructureError("source graph counts differ from its reference")
    if manifest["summary"] != _manifest_summary(references):
        raise StructureError("structure summary is false")


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
        if page["package_path"] is not None:
            package = Path(cast(str, page["package_path"]))
            evidence = _load_json(root, package / "evidence.json", "page evidence")
            lines = _page_lines(evidence, package=package, root=root)
            for line in lines:
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
                    "bbox": line["bbox"],
                    "state": "needs_review" if page["state"] != "ready" else "ready",
                }
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
    return [*native_lines, *ocr_lines]


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
        cast(int, page["pdf_page"])
        for page in cast(list[JsonObject], source_document["pages"])
    ]
    pages = cast(list[JsonObject], graph["pages"])
    if [cast(int, page["pdf_page"]) for page in pages] != expected_pages:
        raise StructureError("source graph page coverage differs from transcription")

    allowed_by_page: dict[int, set[str]] = {}
    for source_page in cast(list[JsonObject], source_document["pages"]):
        page_number = cast(int, source_page["pdf_page"])
        if source_page["package_path"] is None:
            allowed_by_page[page_number] = set()
            continue
        package = Path(cast(str, source_page["package_path"]))
        evidence = _load_json(
            transcription_root, package / "evidence.json", "page evidence"
        )
        allowed_by_page[page_number] = {
            cast(str, line["span_id"])
            for line in _page_lines(evidence, package=package, root=transcription_root)
        }

    node_ids = [
        cast(str, node["node_id"]) for node in cast(list[JsonObject], graph["nodes"])
    ]
    if len(node_ids) != len(set(node_ids)):
        raise StructureError("source graph repeats a node ID")
    node_set = set(node_ids)
    for node in cast(list[JsonObject], graph["nodes"]):
        parent = node["parent_id"]
        if parent is not None and parent not in node_set:
            raise StructureError("source graph has an orphan node")
        for child in cast(list[str], node["children_ids"]):
            if child not in node_set:
                raise StructureError("source graph has an unknown child node")
        _validate_anchors(node, allowed_by_page=allowed_by_page)
    for collection in ("tables", "formulas", "units"):
        for record in cast(list[JsonObject], graph[collection]):
            _validate_anchors(record, allowed_by_page=allowed_by_page)
    for formula in cast(list[JsonObject], graph["formulas"]):
        crop = cast(JsonObject, formula["crop"])
        read_attested_bytes(
            safe_path(transcription_root, cast(str, crop["path"])),
            expected_sha256=cast(str, crop["sha256"]),
            expected_bytes=cast(int, crop["bytes"]),
        )
    if graph["counts"] != _graph_counts(graph):
        raise StructureError("source graph counts are false")


def _validate_anchors(record: JsonObject, *, allowed_by_page: dict[int, set[str]]) -> None:
    page = cast(int, record["pdf_page"])
    anchors = cast(list[str], record["source_span_ids"])
    if not anchors or any(
        anchor not in allowed_by_page.get(page, set()) for anchor in anchors
    ):
        raise StructureError("source graph contains an unknown span anchor")


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
