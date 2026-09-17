"""Reconcile validator decisions against both immutable blind responses."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import cast

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import JsonObject


class SemanticReconciliationError(RegulationsError):
    """Raised when a validator decision cannot be traced to the blind passes."""


@dataclass(frozen=True)
class SemanticReconciliation:
    source_candidates: int
    accepted_candidates: int
    merge_decisions: int
    rejected_candidates: int
    deferred_candidates: int
    unaccounted_candidate_ids: tuple[str, ...]

    def as_json(self) -> JsonObject:
        return {
            "source_candidates": self.source_candidates,
            "accepted_candidates": self.accepted_candidates,
            "merge_decisions": self.merge_decisions,
            "rejected_candidates": self.rejected_candidates,
            "deferred_candidates": self.deferred_candidates,
            "unaccounted_candidates": len(self.unaccounted_candidate_ids),
            "unaccounted_candidate_ids": list(self.unaccounted_candidate_ids),
        }


def reconcile_validator(
    validator: JsonObject,
    *,
    pass_a: JsonObject,
    pass_b: JsonObject,
) -> SemanticReconciliation:
    """Prove that validator outputs only classify candidates from Pass A or B."""
    pass_a_ids = _record_ids(pass_a, "candidates")
    pass_b_ids = _record_ids(pass_b, "candidates")
    overlap = sorted(set(pass_a_ids) & set(pass_b_ids))
    if overlap:
        raise SemanticReconciliationError(f"blind passes repeat candidate ID: {overlap[0]}")
    source_ids = set(pass_a_ids) | set(pass_b_ids)

    accepted_ids = _record_ids(validator, "accepted_candidates")
    rejected_ids = _record_ids(validator, "rejected_candidates")
    deferred_ids = _record_ids(validator, "deferred_candidates")
    merge_records = _records(validator, "merged_candidates")

    merge_targets: list[str] = []
    merged_source_ids: list[str] = []
    merge_ids: list[str] = []
    for index, record in enumerate(merge_records):
        merge_ids.append(_required_string(record, "merge_id", index=index))
        merge_targets.append(_required_string(record, "accepted_candidate_id", index=index))
        raw_source_ids = record.get("source_candidate_ids")
        if (
            not isinstance(raw_source_ids, list)
            or not raw_source_ids
            or not all(isinstance(value, str) and value for value in raw_source_ids)
        ):
            raise SemanticReconciliationError(
                f"merged_candidates record {index} has invalid source_candidate_ids"
            )
        source_candidate_ids = cast(list[str], raw_source_ids)
        _reject_duplicates(source_candidate_ids, "merged source candidate")
        merged_source_ids.extend(source_candidate_ids)

    _reject_duplicates(merge_ids, "merge")
    _reject_duplicates(merge_targets, "accepted merge target")
    _reject_duplicates(merged_source_ids, "classified source candidate")

    accepted_set = set(accepted_ids)
    if set(merge_targets) != accepted_set:
        raise SemanticReconciliationError(
            "validator merge targets do not exactly cover accepted candidates"
        )

    classified = [*merged_source_ids, *rejected_ids, *deferred_ids]
    duplicate_decisions = sorted(
        candidate_id for candidate_id, count in Counter(classified).items() if count > 1
    )
    if duplicate_decisions:
        raise SemanticReconciliationError(
            f"source candidate has multiple validator decisions: {duplicate_decisions[0]}"
        )

    unknown = sorted((accepted_set | set(classified)) - source_ids)
    if unknown:
        raise SemanticReconciliationError(
            f"validator decision references unknown candidate: {unknown[0]}"
        )
    unaccounted = tuple(sorted(source_ids - set(classified)))
    return SemanticReconciliation(
        source_candidates=len(source_ids),
        accepted_candidates=len(accepted_ids),
        merge_decisions=len(merge_records),
        rejected_candidates=len(rejected_ids),
        deferred_candidates=len(deferred_ids),
        unaccounted_candidate_ids=unaccounted,
    )


def _records(value: JsonObject, field: str) -> list[JsonObject]:
    raw_records = value.get(field)
    if not isinstance(raw_records, list) or not all(
        isinstance(record, dict) for record in raw_records
    ):
        raise SemanticReconciliationError(f"validator has invalid {field}")
    return [cast(JsonObject, record) for record in raw_records]


def _record_ids(value: JsonObject, field: str) -> list[str]:
    records = _records(value, field)
    result = [
        _required_string(record, "candidate_id", index=index)
        for index, record in enumerate(records)
    ]
    _reject_duplicates(result, field.removesuffix("s"))
    return result


def _required_string(value: JsonObject, field: str, *, index: int) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result:
        raise SemanticReconciliationError(f"record {index} has invalid or missing {field}")
    return result


def _reject_duplicates(values: list[str], description: str) -> None:
    duplicates = sorted(value for value, count in Counter(values).items() if count > 1)
    if duplicates:
        raise SemanticReconciliationError(f"duplicate {description} ID: {duplicates[0]}")
