"""The three-valued vocabulary. Nothing here depends on how a result is transported."""

from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    """A result is never two-valued. INDETERMINATE never becomes PASS.

    `ifctester` reports "the attribute is missing" and "the attribute violates the rule"
    both as a failure. Telling an architect they have 113 code violations when they have 12
    violations and 101 unknowns is the difference this vocabulary exists to make.
    """

    PASS = "PASS"  # noqa: S105 - a verdict, not a credential
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"


class Applicability(StrEnum):
    """Whether the rule had anything to say about this model at all.

    A separate question from status: a rule that matched nothing has established no
    compliance, however green `ifctester` reports it.
    """

    APPLIES = "APPLIES"
    DOES_NOT_APPLY = "DOES_NOT_APPLY"
    UNDETERMINED = "UNDETERMINED_APPLICABILITY"


class ReasonCode(StrEnum):
    """Why an outcome is what it is, as a stable identifier rather than English prose.

    The engine imports no web framework, so it cannot translate. It names the reason and
    the presentation layer renders it in the reader's language; `messages.default_message`
    supplies English for the engine's own command line and for tests.

    The value strings are part of the stored report and of the HTTP API. Renaming one is a
    breaking change to persisted data.
    """

    # The datum needed to judge the rule is not in the model. Always INDETERMINATE.
    ATTRIBUTE_MISSING = "ATTRIBUTE_MISSING"
    ATTRIBUTE_EMPTY = "ATTRIBUTE_EMPTY"
    ATTRIBUTE_NAME_INVALID = "ATTRIBUTE_NAME_INVALID"
    CLASSIFICATION_MISSING = "CLASSIFICATION_MISSING"
    RELATIONSHIP_MISSING = "RELATIONSHIP_MISSING"
    PROPERTY_SET_MISSING = "PROPERTY_SET_MISSING"
    PROPERTY_MISSING = "PROPERTY_MISSING"
    DATA_TYPE_MISMATCH = "DATA_TYPE_MISMATCH"
    MATERIAL_MISSING = "MATERIAL_MISSING"

    # The datum is present and breaks the rule. Always FAIL.
    ENTITY_CLASS_MISMATCH = "ENTITY_CLASS_MISMATCH"
    PREDEFINED_TYPE_MISMATCH = "PREDEFINED_TYPE_MISMATCH"
    ATTRIBUTE_VALUE_MISMATCH = "ATTRIBUTE_VALUE_MISMATCH"
    ATTRIBUTE_VALUE_PROHIBITED = "ATTRIBUTE_VALUE_PROHIBITED"
    CLASSIFICATION_REFERENCE_MISMATCH = "CLASSIFICATION_REFERENCE_MISMATCH"
    CLASSIFICATION_SYSTEM_MISMATCH = "CLASSIFICATION_SYSTEM_MISMATCH"
    CLASSIFICATION_PROHIBITED = "CLASSIFICATION_PROHIBITED"
    RELATIONSHIP_ENTITY_MISMATCH = "RELATIONSHIP_ENTITY_MISMATCH"
    RELATIONSHIP_PREDEFINED_TYPE_MISMATCH = "RELATIONSHIP_PREDEFINED_TYPE_MISMATCH"
    RELATIONSHIP_PROHIBITED = "RELATIONSHIP_PROHIBITED"
    PROPERTY_VALUE_MISMATCH = "PROPERTY_VALUE_MISMATCH"
    PROPERTY_PROHIBITED = "PROPERTY_PROHIBITED"
    MATERIAL_MISMATCH = "MATERIAL_MISMATCH"
    MATERIAL_PROHIBITED = "MATERIAL_PROHIBITED"

    # An ifctester reason this version of the engine does not recognise. INDETERMINATE:
    # we do not assert a violation we cannot justify.
    REASON_UNRECOGNISED = "REASON_UNRECOGNISED"

    # Decided for a specification as a whole, from its subject count and cardinality.
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    NO_SUBJECTS_BUT_REQUIRED = "NO_SUBJECTS_BUT_REQUIRED"
    NO_SUBJECTS_AND_PROHIBITED = "NO_SUBJECTS_AND_PROHIBITED"
    NO_SUBJECTS_NOTHING_CHECKED = "NO_SUBJECTS_NOTHING_CHECKED"
    PROHIBITED_SUBJECTS_PRESENT = "PROHIBITED_SUBJECTS_PRESENT"

    # An `optional` specification with matched subjects but zero requirement facets: it
    # asserted nothing about the elements it matched. Distinct from
    # `NO_SUBJECTS_NOTHING_CHECKED`, whose wording is specifically about zero matched
    # elements -- here elements matched fine, the rule itself just never said what to check
    # about them.
    NO_REQUIREMENTS_NOTHING_ASSERTED = "NO_REQUIREMENTS_NOTHING_ASSERTED"


#: Codes that mean "the model did not carry what the rule needed", as opposed to
#: "the model carried it and it was wrong". Presentation groups on this.
NOT_EVALUABLE_CODES: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.ATTRIBUTE_MISSING,
        ReasonCode.ATTRIBUTE_EMPTY,
        ReasonCode.ATTRIBUTE_NAME_INVALID,
        ReasonCode.CLASSIFICATION_MISSING,
        ReasonCode.RELATIONSHIP_MISSING,
        ReasonCode.PROPERTY_SET_MISSING,
        ReasonCode.PROPERTY_MISSING,
        ReasonCode.DATA_TYPE_MISMATCH,
        ReasonCode.MATERIAL_MISSING,
        ReasonCode.REASON_UNRECOGNISED,
    }
)

#: Reason codes `judge()` (`check.py`) pairs with an INDETERMINATE verdict it reached
#: without inspecting a single entity: a schema mismatch, an applicability that matched
#: zero subjects, or an optional-cardinality specification that matched real subjects but
#: declared no requirement facets. `NO_SUBJECTS_BUT_REQUIRED` (FAIL) and
#: `NO_SUBJECTS_AND_PROHIBITED` (PASS) are deliberately excluded: matching zero subjects
#: there is itself a real, established verdict the engine reached by judging the model, not
#: an absence of evidence.
#:
#: T-0052: this was three hand-copied literals -- here, in `report_markdown.py`, and in
#: `ReportView.tsx` -- and they had already drifted once, in wording if not yet in
#: substance. The reason codes are decided here, in `judge()`, so the predicate over them
#: is owned here too. `report_markdown.py` (same language) imports `established_nothing`
#: below directly; `ReportView.tsx` cannot import Python, so `presentation.localize_report`
#: computes the one wire field (`SpecificationOutcome.established_nothing`) it reads
#: instead of restating this set in TypeScript. `test_report_markdown.py`'s
#: `test_established_nothing_reason_codes_are_total_over_judge` sweeps every combination
#: `judge()` can reach and fails the build if a future zero-evidence code is added upstream
#: and not added here -- the single test that now guards both renderers, because neither
#: restates the set this test is total over.
NOTHING_ESTABLISHED_REASONS: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.SCHEMA_MISMATCH,
        ReasonCode.NO_SUBJECTS_NOTHING_CHECKED,
        ReasonCode.NO_REQUIREMENTS_NOTHING_ASSERTED,
    }
)


def established_nothing(reason_code: ReasonCode | str | None) -> bool:
    """Whether a specification-level `reason_code` means nothing was evaluated at all.

    `None` is a specification that genuinely evaluated something: `judge()` only sets a
    reason code on a branch that returned without inspecting an entity. A code outside
    `NOTHING_ESTABLISHED_REASONS` is a real verdict `judge()` reached by looking at the
    model (a required element absent, a prohibited one present), not an absence of
    evidence, so it is not named here either.
    """
    return reason_code is not None and reason_code in NOTHING_ESTABLISHED_REASONS


#: FAIL, then INDETERMINATE, then PASS (`docs/decisions.md`, "Severity, for a report built
#: on IDS, is the three-valued status"). FAIL leads because it is the only pile where the
#: model carried the datum and broke the rule; INDETERMINATE outranks PASS so an unknown is
#: never buried under a pass.
#:
#: T-0052: the second hand-copied literal this module now owns. `report_markdown.py`
#: (same language) imports this directly. `ReportView.tsx` keeps its own copy: it needs a
#: rank for a `status` value this build has never heard of (`UNKNOWN_STATUS_RANK`, T-0025
#: review Q2 -- a stored report a *newer* engine wrote and an *older* frontend is reading
#: back), which is a client-side forward-compatibility concern this module has no wire
#: format to hand down. `test_report_view_severity_rank_matches_the_engine`
#: (`test_report_markdown.py`) reads that copy back out of the `.tsx` source and fails the
#: build the moment the two disagree on the three known statuses.
SEVERITY_RANK: dict[Status, int] = {Status.FAIL: 0, Status.INDETERMINATE: 1, Status.PASS: 2}
