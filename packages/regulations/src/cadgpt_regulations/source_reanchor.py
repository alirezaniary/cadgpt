"""Optionally audit transcript records against the deterministic T-0027 source graph.

Transcript text is treated as a search key only.  A record becomes eligible for
the audit when its complete line sequence occurs exactly once in the ordered
structural nodes for the cited source pages. This audit is not required for the
transcript-backed rule path.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes, validate_schema
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.transcription import normalize_search_text


class SourceReanchorError(RegulationsError):
    """Raised when a transcript cannot be safely bound to a source graph."""


@dataclass(frozen=True, slots=True)
class ReanchorResult:
    """Anchored transcript plus an auditable decision report."""

    transcript: JsonObject
    report: JsonObject


_RECORD_COLLECTIONS = (
    "sections",
    "clauses",
    "definitions",
    "requirements",
    "prohibitions",
    "permissions",
    "procedures",
    "tables",
    "formulas",
    "references",
    "uncertainties",
)


def reanchor_transcript(transcript: JsonObject, graph: JsonObject) -> ReanchorResult:
    """Optionally bind transcript records to exact structural node sequences.

    Existing anchors are re-attested against the graph.  Empty anchors are
    populated only after an unambiguous contiguous match.  Ambiguous and
    unmatched records remain unanchored and are explicitly reported. The
    transcript-backed rule path does not require this operation.
    """
    _validate_transcript(transcript)
    _validate_graph_identity(transcript, graph)
    pages, nodes = _graph_lines(graph)
    anchored = copy.deepcopy(transcript)
    decisions: list[JsonObject] = []
    for collection in _RECORD_COLLECTIONS:
        records = transcript.get(collection, [])
        if not isinstance(records, list):
            raise SourceReanchorError(f"transcript collection is invalid: {collection}")
        target_records = cast(list[JsonObject], anchored[collection])
        for index, record in enumerate(cast(list[JsonObject], records)):
            target = target_records[index]
            decisions.append(
                _anchor_record(
                    record,
                    target,
                    collection=collection,
                    index=index,
                    pages=pages,
                    nodes=nodes,
                )
            )
    counts = {
        "records": len(decisions),
        "anchored": sum(item["status"] == "anchored" for item in decisions),
        "already_anchored": sum(item["status"] == "already_anchored" for item in decisions),
        "ambiguous": sum(item["status"] == "ambiguous" for item in decisions),
        "unmatched": sum(item["status"] == "unmatched" for item in decisions),
        "invalid_existing_anchor": sum(
            item["status"] == "invalid_existing_anchor" for item in decisions
        ),
    }
    report: JsonObject = {
        "schema_version": "source-reanchor-1.0.0",
        "source": {
            "catalog_key": graph["catalog_key"],
            "source_sha256": graph["source_sha256"],
            "graph_schema_version": graph.get("schema_version"),
        },
        "decisions": decisions,
        "summary": {
            **counts,
            "publishable": counts["records"] > 0
            and counts["ambiguous"] == 0
            and counts["unmatched"] == 0
            and counts["invalid_existing_anchor"] == 0,
        },
    }
    return ReanchorResult(transcript=anchored, report=report)


def report_sha256(report: JsonObject) -> str:
    """Return a stable digest for a re-anchoring decision report."""
    return hashlib.sha256(canonical_bytes(report)).hexdigest()


def _validate_transcript(transcript: JsonObject) -> None:
    try:
        validate_schema(
            transcript,
            load_packaged_json(
                "cadgpt_regulations.schemas", "structured-transcript.schema.json"
            ),
            description="structured transcript",
        )
    except RegulationsError as exc:
        raise SourceReanchorError(str(exc)) from exc


def _validate_graph_identity(transcript: JsonObject, graph: JsonObject) -> None:
    try:
        validate_schema(
            graph,
            load_packaged_json("cadgpt_regulations.schemas", "source-graph.schema.json"),
            description="source graph",
        )
    except RegulationsError as exc:
        raise SourceReanchorError(str(exc)) from exc
    source = cast(JsonObject, transcript["source"])
    for field in ("catalog_key", "source_sha256"):
        if source.get(field) != graph.get(field):
            raise SourceReanchorError(f"transcript and source graph differ at {field}")
    if not isinstance(graph.get("pages"), list) or not isinstance(graph.get("nodes"), list):
        raise SourceReanchorError("source graph has no pages or nodes")


def _graph_lines(
    graph: JsonObject,
) -> tuple[dict[str, JsonObject], dict[int, list[JsonObject]]]:
    pages: dict[str, JsonObject] = {}
    for page in cast(list[JsonObject], graph["pages"]):
        page_id = page.get("page_id")
        if not isinstance(page_id, str) or page_id in pages:
            raise SourceReanchorError("source graph has duplicate or invalid page IDs")
        pages[page_id] = page
    nodes: dict[int, list[JsonObject]] = {}
    page_numbers = {
        cast(int, page["pdf_page"])
        for page in pages.values()
        if isinstance(page.get("pdf_page"), int)
    }
    seen_nodes: set[str] = set()
    seen_spans: set[str] = set()
    for node in cast(list[JsonObject], graph["nodes"]):
        page = node.get("pdf_page")
        span = node.get("source_span_ids")
        node_id = node.get("node_id")
        raw = node.get("raw_text")
        if (
            not isinstance(page, int)
            or not isinstance(node_id, str)
            or not isinstance(raw, str)
            or not isinstance(span, list)
            or len(span) != 1
            or not isinstance(span[0], str)
        ):
            raise SourceReanchorError("source graph contains an invalid line node")
        if page not in page_numbers:
            raise SourceReanchorError("source graph node references an unknown page")
        span_id = cast(str, span[0])
        if node_id in seen_nodes or span_id in seen_spans:
            raise SourceReanchorError("source graph repeats a node or source span")
        seen_nodes.add(node_id)
        seen_spans.add(span_id)
        nodes.setdefault(page, []).append(node)
    for page_nodes in nodes.values():
        page_nodes.sort(key=lambda item: cast(int, item.get("source_order", 0)))
    return pages, nodes


def _anchor_record(
    record: JsonObject,
    target: JsonObject,
    *,
    collection: str,
    index: int,
    pages: dict[str, JsonObject],
    nodes: dict[int, list[JsonObject]],
) -> JsonObject:
    record_id = record.get("record_id", f"{collection}[{index}]")
    page_ids = record.get("source_page_ids")
    if not isinstance(page_ids, list) or not all(
        isinstance(item, str) for item in page_ids
    ):
        return {
            "collection": collection,
            "record_id": record_id,
            "status": "unmatched",
            "reason": "invalid_source_page_ids",
        }
    page_numbers: list[int] = []
    for page_id in cast(list[str], page_ids):
        page = pages.get(page_id)
        if page is None or not isinstance(page.get("pdf_page"), int):
            return {
                "collection": collection,
                "record_id": record_id,
                "status": "unmatched",
                "reason": "unknown_source_page",
            }
        page_numbers.append(cast(int, page["pdf_page"]))
    existing = record.get("source_span_ids", [])
    if not isinstance(existing, list) or not all(
        isinstance(item, str) for item in existing
    ):
        return {
            "collection": collection,
            "record_id": record_id,
            "status": "invalid_existing_anchor",
            "reason": "invalid_source_span_ids",
        }
    ordered_nodes = sorted(
        [node for page in page_numbers for node in nodes.get(page, [])],
        key=lambda node: cast(int, node["source_order"]),
    )
    available = {cast(str, node["source_span_ids"][0]) for node in ordered_nodes}
    if existing:
        if not set(cast(list[str], existing)).issubset(available):
            return {
                "collection": collection,
                "record_id": record_id,
                "status": "invalid_existing_anchor",
                "reason": "span_not_on_source_page",
            }
        existing_spans = cast(list[str], existing)
        span_to_index = {
            cast(str, node["source_span_ids"][0]): index
            for index, node in enumerate(ordered_nodes)
        }
        indexes = [span_to_index[span] for span in existing_spans]
        contiguous = indexes == list(range(indexes[0], indexes[0] + len(indexes)))
        matched = ordered_nodes[indexes[0] : indexes[-1] + 1] if contiguous else []
        source_text = "\n".join(cast(str, node["raw_text"]) for node in matched)
        if not contiguous or _lines(source_text) != _lines(cast(str, record["text_fa"])):
            return {
                "collection": collection,
                "record_id": record_id,
                "status": "invalid_existing_anchor",
                "reason": "existing_spans_do_not_match_record_text",
            }
        target["source_span_ids"] = existing_spans
        target["source_node_ids"] = [cast(str, node["node_id"]) for node in matched]
        target["exact_text_fa"] = source_text
        target["exact_text_sha256"] = hashlib.sha256(
            source_text.encode("utf-8")
        ).hexdigest()
        return {
            "collection": collection,
            "record_id": record_id,
            "status": "already_anchored",
            "source_span_ids": existing_spans,
            "source_node_ids": [cast(str, node["node_id"]) for node in matched],
            "exact_text_fa": source_text,
            "exact_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        }
    text = record.get("text_fa")
    if not isinstance(text, str) or not text.strip():
        return {
            "collection": collection,
            "record_id": record_id,
            "status": "unmatched",
            "reason": "missing_text_fa",
        }
    target_lines = _lines(text)
    normalized_nodes = [_normalized(cast(str, node["raw_text"])) for node in ordered_nodes]
    matches: list[tuple[int, int]] = []
    width = len(target_lines)
    if width:
        for start in range(0, len(normalized_nodes) - width + 1):
            if normalized_nodes[start : start + width] == target_lines:
                matches.append((start, start + width))
    if len(matches) != 1:
        status = "ambiguous" if len(matches) > 1 else "unmatched"
        reason = (
            "multiple_exact_matches" if len(matches) > 1 else "no_exact_contiguous_match"
        )
        return {
            "collection": collection,
            "record_id": record_id,
            "status": status,
            "reason": reason,
            "matches": len(matches),
        }
    start, end = matches[0]
    matched = ordered_nodes[start:end]
    spans = [cast(str, node["source_span_ids"][0]) for node in matched]
    node_ids = [cast(str, node["node_id"]) for node in matched]
    source_text = "\n".join(cast(str, node["raw_text"]) for node in matched)
    target["source_span_ids"] = spans
    target["source_node_ids"] = node_ids
    target["exact_text_fa"] = source_text
    target["exact_text_sha256"] = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    return {
        "collection": collection,
        "record_id": record_id,
        "status": "anchored",
        "source_span_ids": spans,
        "source_node_ids": node_ids,
        "exact_text_fa": source_text,
        "exact_text_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
    }


def _lines(text: str) -> list[str]:
    return [_normalized(line) for line in text.splitlines() if line.strip()]


def _normalized(text: str) -> str:
    return normalize_search_text(text)[0].strip()
