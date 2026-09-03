from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.extraction_ingest import (
    ingest_extraction_response,
    ingest_validator_response,
)
from cadgpt_regulations.extraction_jobs import build_extraction_jobs
from cadgpt_regulations.semantic_publish import (
    SemanticPublishError,
    _candidate_quality_codes,
    _deduplicate_rules,
    _internet_verification,
    build_semantic_publication,
    validate_semantic_publication,
)


def _write_json(path: Path, value: object) -> tuple[str, int]:
    payload = (json.dumps(value, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(0o600)
    return hashlib.sha256(payload).hexdigest(), len(payload)


def _publication_fixture(
    tmp_path: Path,
) -> tuple[dict[str, object], Path, Path, dict[str, object]]:
    transcription_root = tmp_path / "transcription"
    transcription_root.mkdir(mode=0o700)
    extraction_root = tmp_path / "extraction"
    extraction_root.mkdir(mode=0o700)
    source_sha256 = next(
        artifact["expected_sha256"]
        for artifact in load_catalog()["artifacts"]
        if artifact["catalog_key"] == "volume-01-edition-1392"
    )
    span_id = f"sha256:{source_sha256}:page:000001:native:line:000000"
    for name, payload in (
        ("normalized.txt", b"source\n"),
        ("raw-native.txt", b"source\n"),
        ("model.jpg", b"jpeg"),
    ):
        path = transcription_root / "pages" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(0o600)

    catalog_key = "volume-01-edition-1392"
    bundle_id = f"sha256:{source_sha256}:bundle:000001-000001:test"
    bundle = {
        "bundle_id": bundle_id,
        "catalog_key": catalog_key,
        "source_sha256": source_sha256,
        "sequence": 1,
        "start_pdf_page": 1,
        "end_pdf_page": 1,
        "page_count": 1,
        "input_bytes": 11,
        "pages": [
            {
                "pdf_page": 1,
                "span_ids": [span_id],
                "normalized_text_path": "pages/normalized.txt",
                "raw_native_text_path": "pages/raw-native.txt",
                "model_render_path": "pages/model.jpg",
                "input_bytes": 11,
            }
        ],
        "continuation_edges": [],
    }
    bundle_path = Path("bundles/bundle.json")
    bundle_sha256, _ = _write_json(transcription_root / bundle_path, bundle)
    transcription = {
        "documents": [
            {
                "catalog_key": catalog_key,
                "catalog_order": 1,
                "source_sha256": source_sha256,
                "bundles": [
                    {
                        "bundle_id": bundle_id,
                        "sequence": 1,
                        "start_pdf_page": 1,
                        "end_pdf_page": 1,
                        "page_count": 1,
                        "input_bytes": 11,
                        "path": bundle_path.as_posix(),
                        "sha256": bundle_sha256,
                    }
                ],
            }
        ]
    }
    jobs = build_extraction_jobs(transcription, root=transcription_root)

    response_paths: dict[str, Path] = {}
    ingested = {}
    for pass_label, prefix in (("A", "a"), ("B", "b")):
        response = {
            "schema_version": "1.0.0",
            "input_bundle_sha256": bundle_sha256,
            "pass": pass_label,
            "pages": [1],
            "candidates": [
                {
                    "candidate_id": f"candidate-{prefix}-ready",
                    "kind": "requirement",
                    "subject": "Fire door",
                    "predicate": "must remain closed",
                    "modality": "must",
                    "conditions": [],
                    "exceptions": [],
                    "references": [],
                    "formula_or_table_notes": [],
                    "english_gloss": "The fire door must remain closed.",
                    "uncertainty_codes": [],
                    "source_span_ids": [span_id],
                    "qualifier_span_ids": [],
                },
                {
                    "candidate_id": f"candidate-{prefix}-uncertain",
                    "kind": "requirement",
                    "subject": "Fire door",
                    "predicate": "must meet the stated rating",
                    "modality": "must",
                    "conditions": [],
                    "exceptions": [],
                    "references": [],
                    "formula_or_table_notes": [],
                    "english_gloss": "The fire door must meet the stated rating.",
                    "uncertainty_codes": ["FORMULA_AMBIGUOUS"],
                    "source_span_ids": [span_id],
                    "qualifier_span_ids": [],
                },
                {
                    "candidate_id": f"candidate-{prefix}-generic",
                    "kind": "scope",
                    "subject": "Page 1",
                    "predicate": "presents provisions concerning",
                    "modality": "states",
                    "conditions": [],
                    "exceptions": [],
                    "references": [],
                    "formula_or_table_notes": [],
                    "english_gloss": "Page-level regulation summary.",
                    "uncertainty_codes": [],
                    "source_span_ids": [span_id],
                    "qualifier_span_ids": [],
                },
            ],
        }
        response_path = tmp_path / f"pass-{pass_label}.json"
        _write_json(response_path, response)
        response_paths[pass_label] = response_path
        job = next(job for job in jobs["jobs"] if job["pass"] == pass_label)
        ingested[pass_label] = ingest_extraction_response(
            jobs,
            job_id=job["job_id"],
            response_path=response_path,
            transcription_root=transcription_root,
            output_root=extraction_root,
        )

    pass_b = json.loads(response_paths["B"].read_text())
    validator = {
        "schema_version": "1.0.0",
        "input_bundle_sha256": bundle_sha256,
        "pages": [1],
        "provenance": {
            "bundle_id": bundle_id,
            "bundle_sha256": bundle_sha256,
            "pass_a_sha256": ingested["A"].response_sha256,
            "pass_b_sha256": ingested["B"].response_sha256,
        },
        "accepted_candidates": pass_b["candidates"],
        "merged_candidates": [
            {
                "merge_id": "merge-ready",
                "accepted_candidate_id": "candidate-b-ready",
                "source_candidate_ids": ["candidate-a-ready", "candidate-b-ready"],
            },
            {
                "merge_id": "merge-uncertain",
                "accepted_candidate_id": "candidate-b-uncertain",
                "source_candidate_ids": [
                    "candidate-a-uncertain",
                    "candidate-b-uncertain",
                ],
            },
            {
                "merge_id": "merge-generic",
                "accepted_candidate_id": "candidate-b-generic",
                "source_candidate_ids": [
                    "candidate-a-generic",
                    "candidate-b-generic",
                ],
            },
        ],
        "rejected_candidates": [],
        "deferred_candidates": [],
        "counts": {"accepted": 3, "merged": 3, "rejected": 0, "deferred": 0},
    }
    validator_path = tmp_path / "validator.json"
    _write_json(validator_path, validator)
    ingest_validator_response(
        jobs,
        bundle_id=bundle_id,
        response_path=validator_path,
        transcription_root=transcription_root,
        output_root=extraction_root,
    )

    structure_root = tmp_path / "structure"
    structure_root.mkdir(mode=0o700)
    graph = {
        "catalog_key": catalog_key,
        "catalog_order": 1,
        "source_sha256": source_sha256,
        "pages": [
            {
                "page_id": f"sha256:{source_sha256}:page:000001",
                "pdf_page": 1,
                "state": "needs_review",
                "reason_codes": ["OCR_REVIEW"],
            }
        ],
        "nodes": [],
        "continuation_edges": [],
        "formulas": [
            {
                "formula_id": f"sha256:{source_sha256}:page:000001:equation:0000",
                "pdf_page": 1,
                "source_span_ids": [span_id],
                "latex": None,
                "presentation_mathml": "<math><mi>x</mi></math>",
                "parse_status": "needs_review",
            }
        ],
        "tables": [
            {
                "table_id": f"sha256:{source_sha256}:page:000001:table:0000",
                "pdf_page": 1,
                "source_span_ids": [span_id],
                "rows": [],
                "state": "needs_review",
            }
        ],
        "units": [
            {
                "unit_id": f"sha256:{source_sha256}:page:000001:unit:0000",
                "pdf_page": 1,
                "source_span_ids": [span_id],
                "printed": "m",
                "ucum_code": "m",
                "mapping_status": "mapped",
            }
        ],
        "counts": {
            "pages": 1,
            "nodes": 0,
            "tables": 1,
            "formulas": 1,
            "units": 1,
            "continuation_edges": 0,
            "needs_review": 3,
        },
    }
    graph_path = Path("graphs/graph.json")
    graph_sha256, graph_bytes = _write_json(structure_root / graph_path, graph)
    structure = {
        "documents": [
            {
                "catalog_key": catalog_key,
                "catalog_order": 1,
                "source_sha256": source_sha256,
                "path": graph_path.as_posix(),
                "sha256": graph_sha256,
                "bytes": graph_bytes,
            }
        ],
        "summary": {"formulas": 1, "tables": 1, "units": 1, "needs_review": 3},
    }
    return jobs, extraction_root, structure_root, structure


def test_publication_separates_engine_rules_from_deferred_data(tmp_path: Path) -> None:
    jobs, extraction_root, structure_root, structure = _publication_fixture(tmp_path)
    output_root = tmp_path / "publication"
    output_root.mkdir(mode=0o700)

    first = build_semantic_publication(
        load_catalog(),
        jobs,
        structure,
        extraction_root=extraction_root,
        structure_root=structure_root,
        output_root=output_root,
    )
    second = build_semantic_publication(
        load_catalog(),
        jobs,
        structure,
        extraction_root=extraction_root,
        structure_root=structure_root,
        output_root=output_root,
    )

    assert first.manifest["complete"] is True
    assert first.manifest["summary"]["rules"] == 1
    assert first.manifest["summary"]["duplicate_rules_collapsed"] == 0
    assert first.manifest["summary"]["documents_internet_verified"] == 0
    assert first.manifest["summary"]["formulas"] == 1
    assert first.manifest["summary"]["tables"] == 1
    assert first.manifest["summary"]["units"] == 1
    assert first.manifest["summary"]["deferred"] == 5
    assert second.files_reused == 10
    rule = json.loads((first.run_directory / "rules.jsonl").read_text())
    assert rule["candidate"]["candidate_id"] == "candidate-b-ready"
    assert rule["validation_decision"]["merge_id"] == "merge-ready"
    deferred = [
        json.loads(line)
        for line in (first.run_directory / "deferred.jsonl").read_text().splitlines()
    ]
    assert {record["reason_code"] for record in deferred} == {
        "ACCEPTED_CANDIDATE_HAS_UNCERTAINTY",
        "ACCEPTED_CANDIDATE_FAILED_QUALITY_GATE",
        "FORMULA_REQUIRES_REVIEW",
        "TABLE_REQUIRES_REVIEW",
        "PAGE_TRANSCRIPTION_REQUIRES_REVIEW",
    }
    documents = json.loads((first.run_directory / "documents.json").read_text())
    assert all(
        document["internet_verification"]["status"] == "catalog_only"
        for document in documents["documents"]
    )
    validate_semantic_publication(first.manifest, root=first.run_directory)


def test_publication_requires_acquisition_receipt_and_root_together(
    tmp_path: Path,
) -> None:
    jobs, extraction_root, structure_root, structure = _publication_fixture(tmp_path)
    output_root = tmp_path / "publication"
    output_root.mkdir(mode=0o700)

    with pytest.raises(
        SemanticPublishError,
        match="acquisition receipt and acquisition root must be supplied together",
    ):
        build_semantic_publication(
            load_catalog(),
            jobs,
            structure,
            acquisition={},
            extraction_root=extraction_root,
            structure_root=structure_root,
            output_root=output_root,
        )


def test_internet_verification_preserves_official_transport_evidence() -> None:
    artifact = load_catalog()["artifacts"][0]
    transport = {
        "requested_url": artifact["download_url"],
        "resolved_url": artifact["download_url"],
        "redirect_chain": [artifact["download_url"]],
        "http_status": 200,
        "attempts": 1,
        "sha256": artifact["expected_sha256"],
        "bytes": artifact["expected_bytes"],
        "detected_media_type": artifact["expected_media_type"],
        "pdf_page_count": artifact["expected_pdf_pages"],
    }

    evidence = _internet_verification(
        artifact,
        {"state": "ready", "initial_transport": transport},
    )

    assert evidence["status"] == "transport_verified"
    assert evidence["http_status"] == 200
    assert evidence["sha256"] == artifact["expected_sha256"]
    assert evidence["pdf_page_count"] == artifact["expected_pdf_pages"]


def test_overlapping_bundle_rules_collapse_and_keep_validator_evidence() -> None:
    source_span = "sha256:" + "a" * 64 + ":page:000403:ocr:line:000001"
    candidate = {
        "candidate_id": "candidate-1",
        "kind": "requirement",
        "subject": "Wall spacing",
        "predicate": "limits spacing to 250 mm",
        "modality": "must",
        "comparator": "<=",
        "value": 250,
        "printed_unit": "mm",
        "conditions": [],
        "exceptions": [],
        "references": [],
        "formula_or_table_notes": [],
        "english_gloss": "Wall spacing must not exceed 250 mm.",
        "uncertainty_codes": [],
        "source_span_ids": [source_span],
        "qualifier_span_ids": [],
    }
    first = {
        "record_id": "rule-1",
        "provenance": {"catalog_key": "volume-09", "bundle_id": "bundle-1"},
        "validation_decision": {"merge_id": "merge-1"},
        "corroborating_validations": [],
        "candidate": candidate,
    }
    second = {
        **first,
        "record_id": "rule-2",
        "provenance": {"catalog_key": "volume-09", "bundle_id": "bundle-2"},
        "validation_decision": {"merge_id": "merge-2"},
        "candidate": {
            **candidate,
            "candidate_id": "candidate-2",
            "predicate": "requires wall spacing of no more than 250 mm",
        },
    }

    rules, collapsed = _deduplicate_rules([first, second])

    assert collapsed == 1
    assert len(rules) == 1
    assert rules[0]["corroborating_validations"] == [
        {
            "record_id": "rule-2",
            "provenance": second["provenance"],
            "validation_decision": second["validation_decision"],
            "candidate_id": "candidate-2",
            "predicate": "requires wall spacing of no more than 250 mm",
        }
    ]


def test_quality_gate_rejects_placeholder_semantics_in_qualifiers() -> None:
    candidate = {
        "candidate_id": "placeholder",
        "kind": "requirement",
        "subject": "beam",
        "predicate": "has an actual-looking predicate",
        "modality": "must",
        "conditions": ["when the stated source condition applies"],
        "exceptions": [],
        "references": [],
        "formula_or_table_notes": [],
        "english_gloss": "The beam has an actual-looking requirement.",
        "uncertainty_codes": [],
        "source_span_ids": ["sha256:" + "a" * 64 + ":page:000001:ocr:line:000001"],
        "qualifier_span_ids": [],
    }

    assert "GENERIC_PAGE_SUMMARY" in _candidate_quality_codes(candidate)
