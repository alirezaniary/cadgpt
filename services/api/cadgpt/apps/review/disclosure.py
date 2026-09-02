"""The I7 disclosure: what a report checked, and what it did not.

`prd.md` 5.7 closes on a requirement this product did not meet until this task: "what is
checked is the model; what is submitted is sheets." An office that models the geometry but
drafts its documentation in 2D over it can submit a drawing set that diverges from the
model this system measured, and I7 forbids letting "the model complies" be read as "the
submission complies." The report already names the model it checked (`ifc_filename`, on
every stored document); this module supplies the sentence that says what that naming
means, the same way `reasons.label_for` supplies wording for a `ReasonCode` and
`requirements.requirement_text` supplies wording for a structured basis.

This lives here, not in the frontend catalogue, because report prose belongs to the server
that renders the report -- `docs/decisions.md`, "Report prose belongs to the server, not to
the frontend catalogue." A Celery worker and, eventually, T-0032's generated Markdown file
both need this exact sentence; a `services/web` i18n catalogue is reachable from neither.
`services/review/services/presentation.py` calls this at read time, the same moment it
calls `label_for` and `requirement_text`, so the stored document stays language-neutral and
a translation fix does not require rewriting history.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

#: The disclosure heading, above the coverage block.
_TITLE = _("What this report checked")

#: The disclosure paragraph. Names the model by the filename the architect uploaded
#: (`%(filename)s`, interpolated from the stored report's own `ifc_filename` -- never
#: hardcoded); states plainly that the model, not the submitted drawing set, was checked;
#: names concrete ways the two diverge, because an abstract disclaimer reads as boilerplate
#: and a concrete one reads as information; and never implies the divergence is small,
#: unlikely, or the reader's fault. "The result below" rather than "a clean result below"
#: on purpose -- the word "clean" printed a counterfactual on a FAIL or INDETERMINATE
#: report, which is the live I7 misreading in the other direction: an unlisted remainder
#: read as compliant because the visible line implied a clean run was the one being shown.
_TEXT = _(
    "This report checked the model %(filename)s — not the drawing set your office "
    "submits for review. A model and its submitted drawing set can diverge: detailing "
    "drawn directly onto a view, a schedule typed by hand, an area table in a "
    "titleblock. None of that divergence is checked here. The result below describes "
    "the model; it says nothing about the sheets."
)


def disclosure_title() -> str:
    """The disclosure heading, in the reader's language."""
    return str(_TITLE)


def disclosure_text(ifc_filename: str) -> str:
    """The disclosure paragraph, in the reader's language, naming `ifc_filename`."""
    return str(_TEXT) % {"filename": ifc_filename}
