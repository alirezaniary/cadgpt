"""English text for each `ReasonCode`, for the engine's own output and for tests.

This is a fallback, not the presentation layer. A localized deployment maps `ReasonCode`
to its own catalogue: the code is the contract, the wording is not. Keeping the mapping
total is enforced by a test that walks every member of the enum.
"""

from __future__ import annotations

from cadgpt_engine.status import ReasonCode

_MESSAGES: dict[ReasonCode, str] = {
    ReasonCode.ATTRIBUTE_MISSING: (
        "The attribute the rule needs is not present on the element."
    ),
    ReasonCode.ATTRIBUTE_EMPTY: "The attribute is present but holds no value.",
    ReasonCode.ATTRIBUTE_NAME_INVALID: (
        "The rule names an attribute that does not exist on this entity."
    ),
    ReasonCode.CLASSIFICATION_MISSING: "The element carries no classification.",
    ReasonCode.RELATIONSHIP_MISSING: "The element carries no such relationship.",
    ReasonCode.PROPERTY_SET_MISSING: "The property set the rule needs is not present.",
    ReasonCode.PROPERTY_MISSING: (
        "The property set does not contain the property the rule needs."
    ),
    ReasonCode.DATA_TYPE_MISMATCH: (
        "The value is recorded in a data type the rule cannot compare."
    ),
    ReasonCode.MATERIAL_MISSING: "The element has no material assigned.",
    ReasonCode.ENTITY_CLASS_MISMATCH: (
        "The element is not of the IFC class the rule requires."
    ),
    ReasonCode.PREDEFINED_TYPE_MISMATCH: (
        "The predefined type is not the one the rule requires."
    ),
    ReasonCode.ATTRIBUTE_VALUE_MISMATCH: "The attribute value does not satisfy the rule.",
    ReasonCode.ATTRIBUTE_VALUE_PROHIBITED: (
        "The attribute value matches something the rule prohibits."
    ),
    ReasonCode.CLASSIFICATION_REFERENCE_MISMATCH: (
        "The classification reference does not satisfy the rule."
    ),
    ReasonCode.CLASSIFICATION_SYSTEM_MISMATCH: (
        "The classification system is not the one the rule requires."
    ),
    ReasonCode.CLASSIFICATION_PROHIBITED: (
        "The classification matches something the rule prohibits."
    ),
    ReasonCode.RELATIONSHIP_ENTITY_MISMATCH: (
        "The element is related to entities the rule does not allow."
    ),
    ReasonCode.RELATIONSHIP_PREDEFINED_TYPE_MISMATCH: (
        "The related entity has a predefined type the rule does not allow."
    ),
    ReasonCode.RELATIONSHIP_PROHIBITED: (
        "The relationship matches something the rule prohibits."
    ),
    ReasonCode.PROPERTY_VALUE_MISMATCH: "The property value does not satisfy the rule.",
    ReasonCode.PROPERTY_PROHIBITED: (
        "The property value matches something the rule prohibits."
    ),
    ReasonCode.MATERIAL_MISMATCH: "The material does not satisfy the rule.",
    ReasonCode.MATERIAL_PROHIBITED: "The material matches something the rule prohibits.",
    ReasonCode.REASON_UNRECOGNISED: (
        "The checker reported a result this version of the engine does not recognise, "
        "so it is not asserted as a violation."
    ),
    ReasonCode.SCHEMA_MISMATCH: (
        "The rule is written for a different IFC schema than this model uses, so whether "
        "it applies could not be established."
    ),
    ReasonCode.NO_SUBJECTS_BUT_REQUIRED: (
        "The rule requires matching elements and the model contains none."
    ),
    ReasonCode.NO_SUBJECTS_AND_PROHIBITED: (
        "The rule prohibits such elements and the model contains none."
    ),
    ReasonCode.NO_SUBJECTS_NOTHING_CHECKED: (
        "No element matched this rule, so nothing was checked. The model may contain none, "
        "or may not describe them the way the rule expects."
    ),
    ReasonCode.PROHIBITED_SUBJECTS_PRESENT: (
        "The rule prohibits these elements and the model contains them."
    ),
}


def default_message(code: ReasonCode) -> str:
    """English for `code`. Total over the enum; a missing entry is a bug, not a blank."""
    return _MESSAGES[code]
