"""Render a stored report for a reader, in their language.

The document in the database holds reason codes and no prose. This adds the wording at
read time, which is what lets the same run be read in Persian and in English without
storing it twice or losing the ability to improve a translation.
"""

from __future__ import annotations

from typing import Any

from cadgpt.apps.review.reasons import label_for
from cadgpt.apps.review.requirements import requirement_text


def localize_report(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return `report` with a `reason_label` beside every `reason_code`, and a
    `requirement_text` beside every requirement's `description` / `basis`.

    The stored document is not modified: a copy is annotated, so a translation never
    reaches the database and the run stays reproducible from its inputs.
    """
    if report is None:
        return None

    specifications = []
    for spec in report.get("specifications", []):
        requirements = []
        for requirement in spec.get("requirements", []):
            entities = [
                {**entity, "reason_label": label_for(entity.get("reason_code"))}
                for entity in requirement.get("entities", [])
            ]
            requirements.append(
                {
                    **requirement,
                    "requirement_text": requirement_text(
                        requirement.get("basis"), requirement.get("description", "")
                    ),
                    "entities": entities,
                }
            )
        specifications.append(
            {
                **spec,
                "reason_label": label_for(spec.get("reason_code")),
                "requirements": requirements,
            }
        )

    return {**report, "specifications": specifications}
