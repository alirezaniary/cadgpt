"""Validation and canonical helpers for rule source citations.

The citation is deliberately independent of semantic publication and engine code so
it can be used while building, reviewing, or compiling a rule artifact.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cadgpt_regulations.errors import ManifestError, RegulationsError
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes, validate_schema
from cadgpt_regulations.resources import load_packaged_json


class SourceCitationError(RegulationsError):
    """Raised when a source citation is incomplete or internally inconsistent."""


_CITATION_STATUSES = frozenset(
    {"verified", "pending", "unresolved", "conflicting", "deferred"}
)
_EVIDENCE_KINDS = frozenset({"source_graph", "transcript"})
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def citation_evidence_kind(citation: Mapping[str, Any]) -> str:
    """Return the explicit evidence kind or infer transcript evidence from its identity."""
    explicit = citation.get("evidence_kind")
    if isinstance(explicit, str) and explicit:
        return explicit
    if (
        not citation.get("source_node_ids", [])
        and not citation.get("source_span_ids", [])
        and citation.get("transcript_revision_id")
        and citation.get("transcript_sha256")
    ):
        return "transcript"
    return "source_graph"


def exact_text_sha256(exact_text_fa: str) -> str:
    """Return the hash used by the citation contract for exact Persian text."""
    return hashlib.sha256(exact_text_fa.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceCitation:
    """An immutable, source-pinned citation carried by an executable rule."""

    document_key: str
    book_title_fa: str
    edition_fa: str
    document_sha256: str
    pdf_page: int
    printed_page_label: str | None
    page_id: str
    source_node_ids: tuple[str, ...]
    source_span_ids: tuple[str, ...]
    exact_text_fa: str
    exact_text_sha256: str
    qualifier_text_fa: str | None
    citation_status: str
    evidence_kind: str = "source_graph"
    transcript_revision_id: str | None = None
    transcript_sha256: str | None = None

    @classmethod
    def from_mapping(
        cls,
        citation: Mapping[str, Any],
        *,
        verify_text_hash: bool = True,
    ) -> SourceCitation:
        """Validate a mapping and construct an immutable citation value.

        ``verify_text_hash`` exists for migrations that need to read a legacy record;
        new publication code should leave it enabled (the default).
        """
        value = dict(citation)
        try:
            validate_source_citation(value)
        except (ManifestError, SourceCitationError) as exc:
            if isinstance(exc, SourceCitationError):
                raise
            raise SourceCitationError(str(exc)) from exc

        expected_hash = exact_text_sha256(value["exact_text_fa"])
        if verify_text_hash and value["exact_text_sha256"] != expected_hash:
            raise SourceCitationError(
                "exact_text_sha256 does not match exact_text_fa UTF-8 bytes"
            )
        return cls(
            document_key=value["document_key"],
            book_title_fa=value["book_title_fa"],
            edition_fa=value["edition_fa"],
            document_sha256=value["document_sha256"],
            pdf_page=value["pdf_page"],
            printed_page_label=value.get("printed_page_label"),
            page_id=value.get("page_id") or f"pdf-page:{value['pdf_page']}",
            source_node_ids=tuple(value.get("source_node_ids", [])),
            source_span_ids=tuple(value.get("source_span_ids", [])),
            exact_text_fa=value["exact_text_fa"],
            exact_text_sha256=value["exact_text_sha256"],
            qualifier_text_fa=value["qualifier_text_fa"],
            citation_status=value["citation_status"],
            evidence_kind=citation_evidence_kind(value),
            transcript_revision_id=value.get("transcript_revision_id"),
            transcript_sha256=value.get("transcript_sha256"),
        )

    def to_mapping(self) -> JsonObject:
        """Return the canonical JSON-compatible citation representation."""
        result: JsonObject = {
            "document_key": self.document_key,
            "book_title_fa": self.book_title_fa,
            "edition_fa": self.edition_fa,
            "document_sha256": self.document_sha256,
            "pdf_page": self.pdf_page,
            "printed_page_label": self.printed_page_label,
            "page_id": self.page_id,
            "source_node_ids": list(self.source_node_ids),
            "source_span_ids": list(self.source_span_ids),
            "exact_text_fa": self.exact_text_fa,
            "exact_text_sha256": self.exact_text_sha256,
            "qualifier_text_fa": self.qualifier_text_fa,
            "citation_status": self.citation_status,
        }
        if self.evidence_kind != "source_graph":
            result["evidence_kind"] = self.evidence_kind
            result["transcript_revision_id"] = self.transcript_revision_id
            result["transcript_sha256"] = self.transcript_sha256
        return result

    def canonical_bytes(self) -> bytes:
        """Return the stable JSON bytes used in release artifacts and hashes."""
        return canonical_bytes(self.to_mapping())


def validate_source_citation(
    citation: JsonObject, *, description: str = "source citation"
) -> None:
    """Validate citation shape and transcript/document identity.

    The JSON Schema checks types and required fields; these semantic checks make the
    contract explicit for callers that only need validation and not a value object.
    Structural node/span IDs are optional metadata for transcript evidence. Transcript
    evidence is identified by its transcript revision and hash instead; source-graph
    evidence still requires its structural anchors.
    """
    schema = load_packaged_json("cadgpt_regulations.schemas", "source-citation.schema.json")
    try:
        validate_schema(citation, schema, description=description)
    except ManifestError as exc:
        raise SourceCitationError(str(exc)) from exc
    if citation["citation_status"] not in _CITATION_STATUSES:
        raise SourceCitationError(
            f"{description} has unsupported citation_status: {citation['citation_status']}"
        )
    if citation["exact_text_sha256"] != exact_text_sha256(citation["exact_text_fa"]):
        raise SourceCitationError(
            f"{description} exact_text_sha256 does not match exact_text_fa"
        )
    evidence_kind = citation_evidence_kind(citation)
    if evidence_kind not in _EVIDENCE_KINDS:
        raise SourceCitationError(f"{description} has unsupported evidence_kind")
    for field in ("source_node_ids", "source_span_ids"):
        values = citation.get(field, [])
        if not isinstance(values, list) or not all(
            isinstance(item, str) and item for item in values
        ):
            raise SourceCitationError(f"{description} {field} must be a list of strings")
        if evidence_kind == "source_graph" and not values:
            raise SourceCitationError(f"{description} {field} must not be empty")
    if evidence_kind == "transcript":
        revision_id = citation.get("transcript_revision_id")
        transcript_hash = citation.get("transcript_sha256")
        if not isinstance(revision_id, str) or not revision_id:
            raise SourceCitationError(
                f"{description} transcript_revision_id is required for transcript evidence"
            )
        if not isinstance(transcript_hash, str) or not _HASH_RE.fullmatch(transcript_hash):
            raise SourceCitationError(
                f"{description} transcript_sha256 is required for transcript evidence"
            )


def source_citation_schema() -> JsonObject:
    """Load the packaged source citation schema for embedding or introspection."""
    return load_packaged_json("cadgpt_regulations.schemas", "source-citation.schema.json")


__all__ = [
    "SourceCitation",
    "SourceCitationError",
    "citation_evidence_kind",
    "exact_text_sha256",
    "source_citation_schema",
    "validate_source_citation",
]
