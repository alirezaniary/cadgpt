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
