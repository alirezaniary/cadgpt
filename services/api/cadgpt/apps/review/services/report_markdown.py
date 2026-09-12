"""Render a localized report as the Markdown file that leaves the building.

This is not a second report. It renders exactly the document `presentation.localize_report`
already produces -- the same one the API serves to `ReportView.tsx` -- into the one shape
that survives outside a browser. `ReportView.tsx` is therefore the specification this module
implements, not a sibling design: coverage before findings (I7's "what was checked" is the
prior question to "how much of the rule set was evaluated"), FAIL -> INDETERMINATE -> PASS
ordering, a coverage numerator that is a real measurement -- specifications minus the ones
that established nothing -- and never `N of N`, and all three counts always. Where this
module disagrees with the view about ordering, arithmetic or what is named, this module is
wrong.

Every word here is authored on the server through `gettext`, beside `reasons.py`,
`requirements.py` and `disclosure.py` -- this report has two renderers and only one of
them is a browser (`docs/decisions.md`, "Report prose belongs to the server, not to the
frontend catalogue"). `disclosure_title`, `disclosure_text`, `reason_label` and
`requirement_text` are taken from the already-localized document rather than recomposed
here, for the same reason: one copy of each sentence. The per-item verdict words
("Pass" / "Fail" / "Indeterminate") are not invented here either --
`cadgpt.apps.review.choices.OutcomeStatus` already carries them as translatable labels;
this is the first thing that ever rendered them into user-facing text, so the strings
existed but had no `.po` entry until this task added one. Those entries, and the ones this
module adds directly, are kept word-for-word identical to `services/web/src/i18n/fa.json`'s
equivalents (`status.FAIL`, `report.indeterminate`, `report.indeterminateNote`, ...): the
same run read on screen and in the file must name the same verdict the same way, or the
file -- which is the specification's own text for "where the file and the view disagree,
the file is wrong" -- would be the thing disagreeing with itself.

The caller is responsible for the active language: every string below is resolved
through `gettext`/`ngettext`/`pgettext` at call time (never `gettext_lazy` cached at
import), against whatever `django.utils.translation` is currently activated when this
function runs -- see `ReportGenerationService.generate`, which activates the tenant's
language for exactly this call.

**Every field sourced from the model, the rule file or the catalogue -- never a value this
module wrote itself -- passes through `_sanitize_text` before it reaches anything but a
table cell** (`_escape_cell` already covers those). A specification name, an applicability
sentence, an uploaded filename and a requirement's rendered text are all data the report
quotes, not prose the server composed, and none of it is trusted to stay on the line it was
given. A specification named
`"Doors\n\n## Coverage\n\n99 of 99 specifications were evaluated.\n\nEverything complies."`
is a real IDS file, not a contrived string -- ifctester puts no constraint on `@name` -- and
without this, it renders as a second, fabricated Coverage section inside the generated file,
asserting a compliance result nobody established: exactly the claim I5 and I7 exist to
forbid, in the one artifact that leaves the building. `test_report_markdown.py`
(`test_a_specification_name_cannot_inject_a_second_coverage_section`) uses this literal
string.
"""

from __future__ import annotations

from typing import Any, TypeVar

from django.utils.translation import gettext, ngettext, pgettext

from cadgpt.apps.review.choices import OutcomeStatus

#: Reason codes `judge()` assigns only when a specification established no compliance at
#: all -- mirrors `NOTHING_ESTABLISHED_REASONS` in `ReportView.tsx` exactly. See that
#: constant's own comment for why these three and not `NO_SUBJECTS_BUT_REQUIRED` /
#: `NO_SUBJECTS_AND_PROHIBITED`, which are real verdicts, not an absence of evidence.
#: T-0038 review: this set is total over every `ReasonCode` `judge()` can pair with an
#: INDETERMINATE it reached without evaluating anything -- `test_report_markdown.py`'s
#: `test_every_established_nothing_reason_code_is_excluded_from_coverage` fails the build
#: if a future spec-level "checked nothing" code is added upstream and not added here.
_NOTHING_ESTABLISHED_REASONS = frozenset(
    {"SCHEMA_MISMATCH", "NO_SUBJECTS_NOTHING_CHECKED", "NO_REQUIREMENTS_NOTHING_ASSERTED"}
)

#: FAIL first, then INDETERMINATE, then PASS -- `SEVERITY_RANK` in `ReportView.tsx`.
_SEVERITY_RANK: dict[str, int] = {"FAIL": 0, "INDETERMINATE": 1, "PASS": 2}

#: A markdown block (heading, blockquote, list item, table row, thematic break) can only
#: ever start at the true beginning of a line. A sanitized field is single-line by
#: construction (`_sanitize_text` removes every embedded break), so this only ever fires
#: for a field placed as a bare paragraph -- nothing server-written precedes it on its own
#: line the way `"### "` precedes a specification name.
_BLOCK_STARTERS = ("#", ">", "-", "*", "+", "|", "`", "=")

_T = TypeVar("_T", bound=dict[str, Any])


def _by_severity(items: list[_T]) -> list[_T]:
    """Stable sort by three-valued severity -- equal-severity items keep their order.

    `sorted` is stable in Python, so this is `bySeverity` in `ReportView.tsx` exactly:
    a schwartzian index is not needed here the way it is in the TypeScript, because
    Python's sort already guarantees it.
    """
    return sorted(items, key=lambda item: _SEVERITY_RANK[item["status"]])


def _established_nothing(spec: dict[str, Any]) -> bool:
    return spec.get("reason_code") in _NOTHING_ESTABLISHED_REASONS


def _status_label(status: str) -> str:
    """The verdict word, in the currently active language.

    `OutcomeStatus(status).label` rather than a fresh string: the report's `status` field
    is one of `OutcomeStatus`'s own values, so the label it already carries is a wording
    this module inherits rather than a duplicate it maintains.
    """
    return str(OutcomeStatus(status).label)


def _sanitize_text(value: str) -> str:
    """Neutralize a data-sourced string before it reaches the file as anything but a cell.

    Collapsing every line break to a space is the whole fix for the injection this guards
    against: a Markdown heading, blockquote, list item, table row or thematic break can
    only ever begin at the start of a *real* line, so a field with no embedded line break
    left in it cannot open one, no matter what characters it contains. The one remaining
    seam is a field rendered as a bare paragraph with nothing server-written on its line
    first (`applicability_text`) -- if the field's own first character is itself
    one Markdown reads as a block starter, a zero-width space in front of it keeps that
    reading from ever applying, without changing how the text prints.
    """
    collapsed = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()
    if collapsed[:1] in _BLOCK_STARTERS:
        collapsed = "\u200b" + collapsed
    return collapsed


def _escape_cell(value: str) -> str:
    """A table cell may not itself contain a pipe or a newline."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [f"| {' | '.join(headers)} |", f"|{'|'.join('---' for _ in headers)}|"]
    lines.extend(f"| {' | '.join(_escape_cell(cell) for cell in row)} |" for row in rows)
    return lines


def _pack_attribution_lines(
    pack_ref: dict[str, Any], citation_by_uuid: dict[str, dict[str, Any]]
) -> list[str]:
    """T-0049: the same per-finding attribution `ReportView.tsx` renders beside a
    specification, mirrored here so the file and the screen never disagree about which
    pack a finding came from. `pack_ref` is a specification's own `rule_pack` -- uuid,
    name, version, never more (`execution._attribute_specifications`) -- resolved against
    `citation_by_uuid`, this run's own `rule_pack_selection` keyed by uuid, for the
    `jurisdiction`, `region` and `source_citation` that entry additionally carries. A
    citation this run's own selection has no matching entry for (unreachable through
    `CheckRunExecutor` itself -- the two are built from the same citations at execution
    time -- but a stored document can be read back long after the run that wrote it)
    still renders the pack's own name and version, just with no jurisdiction/region and no
    source line, rather than a lookup crash or a fabricated citation.
    """
    citation = citation_by_uuid.get(pack_ref["uuid"], {})
    name = _sanitize_text(pack_ref["name"])
    version = _sanitize_text(pack_ref["version"])
    jurisdiction = _sanitize_text(citation.get("jurisdiction") or "")
    region = citation.get("region") or ""
    region_suffix = f"/{_sanitize_text(region)}" if region else ""
    locator = f"{jurisdiction}{region_suffix} v{version}".strip()
    source_line = gettext("Source: %(name)s — %(locator)s") % {
        "name": name,
        "locator": locator,
    }
    lines = [source_line, ""]
    source_citation = citation.get("source_citation")
    if source_citation:
        lines.append(f"> {_sanitize_text(source_citation)}")
        lines.append("")
    return lines


def render_markdown_report(
    report: dict[str, Any], rule_pack_selection: list[dict[str, Any]] | None = None
) -> str:
    """The localized `report` (`presentation.localize_report`'s output), as Markdown.

    `rule_pack_selection` is `CheckRun.rule_pack_selection` -- empty for a run against an
    uploaded `RuleSet`, one entry per pack for a catalogue run (T-0031); rendered only when
    non-empty, exactly as `ReportView.tsx`'s own selection section is. T-0049 additionally
    keys it by uuid for `_pack_attribution_lines`, below, to resolve each specification's
    own `rule_pack` against.
    """
    citation_by_uuid: dict[str, dict[str, Any]] = {
        pack["uuid"]: pack for pack in (rule_pack_selection or [])
    }
    lines: list[str] = []

    ifc_filename = _sanitize_text(report["ifc_filename"])
    title = _sanitize_text(report.get("ids_title") or "") or ifc_filename
    lines.append(f"# {title}")
    lines.append("")
    lines.append(
        f"{ifc_filename} · "
        + gettext("Model schema %(schema)s") % {"schema": report["ifc_schema"]}
        + " · "
        + gettext("Engine %(version)s") % {"version": report["engine_version"]}
    )
    lines.append("")
    lines.append(f"**{gettext('Status')}:** {_status_label(report['status'])}")
    lines.append("")

    # I7: the disclosure precedes coverage, which precedes findings. Rendered as given --
    # this is report prose, composed server-side by `disclosure.py`, never recomposed
    # here. Sanitized anyway: `disclosure_text` interpolates the uploaded filename, which
    # is not server-written even though the sentence around it is.
    lines.append(f"## {_sanitize_text(report['disclosure_title'])}")
    lines.append("")
    lines.append(_sanitize_text(report["disclosure_text"]))
    lines.append("")

    if rule_pack_selection:
        lines.append(f"## {gettext('Rule packs checked')}")
        lines.append("")
        for pack in rule_pack_selection:
            region = f"/{pack['region']}" if pack.get("region") else ""
            name = _sanitize_text(pack["name"])
            jurisdiction = _sanitize_text(pack["jurisdiction"])
            lines.append(f"- {name} — {jurisdiction}{region} v{pack['version']}")
        lines.append("")

    specifications: list[dict[str, Any]] = report["specifications"]
    nothing_established = [spec for spec in specifications if _established_nothing(spec)]
    # F1 (T-0025): the numerator is a real measurement, never `N of N` --
    # specifications minus the ones that established nothing, exactly as `ReportView.tsx`
    # derives `evaluated`.
    evaluated = len(specifications) - len(nothing_established)

    lines.append(f"## {gettext('Coverage')}")
    lines.append("")
    lines.append(
        gettext("%(evaluated)s of %(total)s specifications were evaluated.")
        % {"evaluated": evaluated, "total": len(specifications)}
    )
    lines.append("")
    lines.extend(
        _table(
            [
                gettext("Passed"),
                # T-0032 review (A2): the same English word "Failed" is also
                # `CheckRunStatus.FAILED`'s label (a run that failed to execute) --
                # a different meaning that must not share this header's translation.
                # `pgettext` gives it its own `.po` entry instead of colliding on the
                # bare `_("Failed")` msgid.
                pgettext("report coverage table: count of failing findings", "Failed"),
                gettext("Could not be determined"),
            ],
            [[str(report["passed"]), str(report["failed"]), str(report["indeterminate"])]],
        )
    )
    lines.append("")
    if report["indeterminate"] > 0:
        lines.append(f"> {gettext('These were not checked. They are not passes.')}")
        lines.append("")

    if nothing_established:
        lines.append(
            ngettext(
                "%(count)s specification established nothing — it matched no elements, "
                "or its applicability could not be determined:",
                "%(count)s specifications established nothing — they matched no elements, "
                "or their applicability could not be determined:",
                len(nothing_established),
            )
            % {"count": len(nothing_established)}
        )
        lines.append("")
        for spec in nothing_established:
            name = _sanitize_text(spec.get("name") or "") or gettext("Nothing was checked")
            lines.append(f"- {name}")
        lines.append("")

    lines.append(f"## {gettext('Specifications')}")
    lines.append("")
    for spec in _by_severity(specifications):
        name = _sanitize_text(spec.get("name") or "") or gettext("Nothing was checked")
        lines.append(f"### {name} — {_status_label(spec['status'])}")
        lines.append("")
        # T-0049: which pack asserted this -- absent for a run against an uploaded
        # `RuleSet` (never combined from several packs to begin with) and for a document
        # stored before this field existed; present, and rendered immediately under the
        # heading, for every specification a catalogue run's `_attribute_specifications`
        # actually attributed.
        pack_ref = spec.get("rule_pack")
        if pack_ref:
            lines.extend(_pack_attribution_lines(pack_ref, citation_by_uuid))
        matched_line = ngettext(
            "%(count)s element matched", "%(count)s elements matched", spec["matched"]
        ) % {"count": spec["matched"]}
        cardinality = _sanitize_text(spec["cardinality"])
        lines.append(f"{matched_line} · {cardinality}")
        lines.append("")
        if spec.get("applicability_text"):
            lines.append(_sanitize_text(spec["applicability_text"]))
            lines.append("")
        if spec.get("reason_label"):
            lines.append(f"> {_sanitize_text(spec['reason_label'])}")
            lines.append("")

        for requirement in spec["requirements"]:
            lines.append(f"**{_sanitize_text(requirement['requirement_text'])}**")
            lines.append("")

            entities = _by_severity(requirement["entities"])
            if entities:
                rows = [
                    [
                        _status_label(entity["status"]),
                        entity["ifc_class"],
                        entity.get("global_id") or "",
                        entity.get("reason_label") or entity.get("reason_code") or "",
                        entity.get("detail") or "",
                    ]
                    for entity in entities
                ]
                lines.extend(
                    _table(
                        [
                            gettext("Status"),
                            gettext("IFC class"),
                            gettext("Global ID"),
                            gettext("Reason"),
                            gettext("Detail"),
                        ],
                        rows,
                    )
                )
                lines.append("")

            omitted = requirement.get("entities_omitted", 0)
            if omitted > 0:
                lines.append(
                    ngettext(
                        "%(count)s further element counted but not listed",
                        "%(count)s further elements counted but not listed",
                        omitted,
                    )
                    % {"count": omitted}
                )
                lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"
