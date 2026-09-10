"""Render a stored report for a reader, in their language.

The document in the database holds reason codes and no prose. This adds the wording at
read time, which is what lets the same run be read in Persian and in English without
storing it twice or losing the ability to improve a translation.
"""

from __future__ import annotations

from typing import Any

from cadgpt.apps.review.disclosure import disclosure_text, disclosure_title
from cadgpt.apps.review.reasons import label_for
from cadgpt.apps.review.requirements import requirement_text


def localize_report(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return `report` with a `reason_label` beside every `reason_code` -- an entity's, a
    specification's, and (T-0037) a requirement's own, when it carries one -- an
    `applicability_caveat_label` beside a requirement's `applicability_caveat` (T-0037
    review round 2, F1: a requirement that evaluated real entities under a specification
    whose own applicability was never established), a `requirement_text` beside every
    requirement's `description` / `basis`, and the I7 disclosure (`disclosure_title`,
    `disclosure_text`) naming the model this report checked (`prd.md` 5.7 -- see
    `cadgpt.apps.review.disclosure`).

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
                    # T-0037: `None` for a requirement stored before this field existed
                    # and for one that genuinely evaluated entities alike --
                    # `label_for(None)` returns `None` for both, and the reader cannot
                    # tell the two apart from this field, which is correct: neither has
                    # anything to say.
                    "reason_label": label_for(requirement.get("reason_code")),
                    # T-0037 review round 2 (F1): a requirement that *did* evaluate real
                    # entities but whose specification's own applicability was never
                    # established (a schema mismatch, e.g.) -- a distinct field from
                    # `reason_label` above, reusing the same total `label_for` mapping,
                    # because reusing `reason_label` itself would say "this requirement
                    # evaluated nothing", which would be false here.
                    "applicability_caveat_label": label_for(
                        requirement.get("applicability_caveat")
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

    return {
        **report,
        "specifications": specifications,
        "disclosure_title": disclosure_title(),
        "disclosure_text": disclosure_text(report.get("ifc_filename", "")),
    }
