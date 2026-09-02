"""Translate the engine's reason codes.

The engine imports no web framework, so it cannot call `gettext`. It names each reason
with a stable code and this module supplies the wording, in the reader's language, at the
moment a report is rendered.

Keeping the stored report language-neutral is the point: one run can be read in Persian by
the architect and in English by a consultant, from the same document, and a translation
improvement does not require rewriting history.

The mapping is total over `ReasonCode`, and `tests/test_reasons.py` fails the build if a
new code is added upstream without wording here -- otherwise a new reason would surface to
a user as a bare identifier.
"""

from __future__ import annotations

from typing import Any

from cadgpt_engine import ReasonCode
from django.utils.translation import gettext_lazy as _

#: Every `ReasonCode` to the sentence a user reads. Total over the enum by test.
REASON_LABELS: dict[str, Any] = {
    ReasonCode.ATTRIBUTE_MISSING: _(
        "The attribute this rule needs is not present on the element."
    ),
    ReasonCode.ATTRIBUTE_EMPTY: _("The attribute is present but holds no value."),
    ReasonCode.ATTRIBUTE_NAME_INVALID: _(
        "The rule names an attribute that does not exist on this entity."
    ),
    ReasonCode.CLASSIFICATION_MISSING: _("The element carries no classification."),
    ReasonCode.RELATIONSHIP_MISSING: _("The element carries no such relationship."),
    ReasonCode.PROPERTY_SET_MISSING: _("The property set this rule needs is not present."),
    ReasonCode.PROPERTY_MISSING: _(
        "The property set does not contain the property this rule needs."
    ),
    ReasonCode.DATA_TYPE_MISMATCH: _(
        "The value is recorded in a data type the rule cannot compare."
    ),
    ReasonCode.MATERIAL_MISSING: _("The element has no material assigned."),
    ReasonCode.ENTITY_CLASS_MISMATCH: _(
        "The element is not of the IFC class the rule requires."
    ),
    ReasonCode.PREDEFINED_TYPE_MISMATCH: _(
        "The predefined type is not the one the rule requires."
    ),
    ReasonCode.ATTRIBUTE_VALUE_MISMATCH: _(
        "The attribute value does not satisfy the rule."
    ),
    ReasonCode.ATTRIBUTE_VALUE_PROHIBITED: _(
        "The attribute value matches something the rule prohibits."
    ),
    ReasonCode.CLASSIFICATION_REFERENCE_MISMATCH: _(
        "The classification reference does not satisfy the rule."
    ),
    ReasonCode.CLASSIFICATION_SYSTEM_MISMATCH: _(
        "The classification system is not the one the rule requires."
    ),
    ReasonCode.CLASSIFICATION_PROHIBITED: _(
        "The classification matches something the rule prohibits."
    ),
    ReasonCode.RELATIONSHIP_ENTITY_MISMATCH: _(
        "The element is related to entities the rule does not allow."
    ),
    ReasonCode.RELATIONSHIP_PREDEFINED_TYPE_MISMATCH: _(
        "The related entity has a predefined type the rule does not allow."
    ),
    ReasonCode.RELATIONSHIP_PROHIBITED: _(
        "The relationship matches something the rule prohibits."
    ),
    ReasonCode.PROPERTY_VALUE_MISMATCH: _("The property value does not satisfy the rule."),
    ReasonCode.PROPERTY_PROHIBITED: _(
        "The property value matches something the rule prohibits."
    ),
    ReasonCode.MATERIAL_MISMATCH: _("The material does not satisfy the rule."),
    ReasonCode.MATERIAL_PROHIBITED: _("The material matches something the rule prohibits."),
    ReasonCode.REASON_UNRECOGNISED: _(
        "The checker reported a result this version of the engine does not recognise, "
        "so it is not asserted as a violation."
    ),
    ReasonCode.SCHEMA_MISMATCH: _(
        "This rule is written for a different IFC schema than the model uses, so "
        "whether it applies could not be established."
    ),
    ReasonCode.NO_SUBJECTS_BUT_REQUIRED: _(
        "This rule requires matching elements and the model contains none."
    ),
    ReasonCode.NO_SUBJECTS_AND_PROHIBITED: _(
        "This rule prohibits such elements and the model contains none."
    ),
    ReasonCode.NO_SUBJECTS_NOTHING_CHECKED: _(
        "No element matched this rule, so nothing was checked. The model may contain "
        "none, or may not describe them the way the rule expects."
    ),
    ReasonCode.PROHIBITED_SUBJECTS_PRESENT: _(
        "This rule prohibits these elements and the model contains them."
    ),
}


def label_for(code: str | None) -> str | None:
    """The localized sentence for a reason code, or None when there is no reason.

    An unknown code returns the code itself rather than nothing: a report from a newer
    engine read by an older API should degrade to an identifier, never to a blank line
    that hides why an element did not pass.
    """
    if not code:
        return None
    label = REASON_LABELS.get(code)
    return str(label) if label is not None else code
