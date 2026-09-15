from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.observation_contract import (
    ObservationContractError,
    build_observation_contract,
    resolve_observations,
)

FIXTURE = Path(__file__).parent / "fixtures" / "inbr_transcript_volume10_page586.json"


def _rule() -> dict[str, object]:
    transcript = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = transcript["source"]
    table = transcript["tables"][0]
    exact = table["text_fa"]
    return {
        "schema_version": "rule-ir-1.0.0",
        "rule_key": "fire-factor-derived",
        "source_citation": {
            "document_key": source["catalog_key"],
            "book_title_fa": transcript["title_fa"],
            "edition_fa": "ویرایش ۱۴۰۱",
            "document_sha256": source["source_sha256"],
            "pdf_page": source["start_pdf_page"],
            "printed_page_label": str(source["start_pdf_page"]),
            "page_id": table["source_page_ids"][0],
            "source_node_ids": ["node:volume-10-edition-1401:page:000586:table:0001"],
            "source_span_ids": ["span:volume-10-edition-1401:page:000586:table:0001"],
            "exact_text_fa": exact,
            "exact_text_sha256": hashlib.sha256(exact.encode()).hexdigest(),
            "qualifier_text_fa": None,
            "citation_status": "verified",
        },
    }


def test_observation_contract_retains_inbr_citation_and_indeterminate_state() -> None:
    contract = build_observation_contract(
        _rule(), [{"observation_key": "beam_fire_factor", "kind": "table", "unit": None}]
    )
    result = resolve_observations(contract, {})

    assert contract["status"] == "DEFERRED"
    assert contract["source_citation"]["exact_text_fa"].startswith("جدول")
    assert result["status"] == "INDETERMINATE"
    assert result["observations"][0]["status"] == "INDETERMINATE"


def test_observation_contract_resolves_scalar_value() -> None:
    contract = build_observation_contract(
        _rule(), [{"observation_key": "temperature", "kind": "numeric", "unit": "C"}]
    )

    result = resolve_observations(contract, {"temperature": 540})

    assert result["status"] == "AVAILABLE"
    assert result["observations"][0]["value"] == 540


def test_observation_contract_rejects_duplicate_required_observations() -> None:
    with pytest.raises(ObservationContractError, match="duplicate"):
        build_observation_contract(
            _rule(),
            [
                {"observation_key": "temperature", "kind": "numeric"},
                {"observation_key": "temperature", "kind": "numeric"},
            ],
        )


@pytest.mark.parametrize("value", [[None], {"value": 540}, True, float("nan"), "540"])
def test_numeric_observation_does_not_guess_ambiguous_or_wrong_types(value) -> None:
    contract = build_observation_contract(
        _rule(), [{"observation_key": "temperature", "kind": "numeric", "unit": "Cel"}]
    )
    result = resolve_observations(contract, {"temperature": value})
    assert result["status"] == "INDETERMINATE"
    assert result["source_citation"] == contract["source_citation"]


def test_resolver_rejects_tampered_contract() -> None:
    contract = build_observation_contract(
        _rule(), [{"observation_key": "temperature", "kind": "numeric"}]
    )
    contract["required_observations"][0]["kind"] = "text"
    with pytest.raises(ObservationContractError, match="identity"):
        resolve_observations(contract, {"temperature": "540"})
