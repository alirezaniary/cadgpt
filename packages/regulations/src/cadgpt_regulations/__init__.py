"""Regulation corpus inventory and publication contracts."""

from cadgpt_regulations.acquisition import (
    acquire_corpus,
    check_acquisition_health,
    validate_acquisition_receipt,
)
from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.inventory import build_inventory, write_inventory
from cadgpt_regulations.provisional_batch import (
    ProvisionalBatchError,
    build_provisional_batch,
    validate_provisional_batch,
)
from cadgpt_regulations.provisional_rule import (
    make_candidate_citation,
    make_provisional_rule,
    make_transcript_revision,
    validate_candidate_citation,
    validate_provisional_rule,
    validate_transcript_revision,
)
from cadgpt_regulations.source_citation import (
    SourceCitation,
    SourceCitationError,
    citation_evidence_kind,
    exact_text_sha256,
    validate_source_citation,
)
from cadgpt_regulations.transcript_citation import (
    TranscriptCitationError,
    make_transcript_citation,
    validate_transcript_citation,
)
from cadgpt_regulations.validation import check_publishable, validate_manifest

__all__ = [
    "ProvisionalBatchError",
    "SourceCitation",
    "SourceCitationError",
    "TranscriptCitationError",
    "acquire_corpus",
    "build_inventory",
    "build_provisional_batch",
    "check_acquisition_health",
    "check_publishable",
    "citation_evidence_kind",
    "exact_text_sha256",
    "load_catalog",
    "make_candidate_citation",
    "make_provisional_rule",
    "make_transcript_citation",
    "make_transcript_revision",
    "validate_acquisition_receipt",
    "validate_candidate_citation",
    "validate_manifest",
    "validate_provisional_batch",
    "validate_provisional_rule",
    "validate_source_citation",
    "validate_transcript_citation",
    "validate_transcript_revision",
    "write_inventory",
]
