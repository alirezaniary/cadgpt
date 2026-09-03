# T-0055 — The report file must stand on its own once it leaves the building

**Phase:** 3   **Status:** open
**Touches invariants:** I7 — say what was checked. **Reviewer-gated.**

## Why

Found by the T-0032 review. Both findings are about the same thing: the generated file is read
somewhere we do not control, by someone who has no access to the app, possibly months later.

1. **The file cannot be traced back to its run.** It carries no check date and no run identifier in
   its body — only in the filename, which the frontend currently discards (T-0053). Rename or
   archive the file and there is no way to establish which run produced it, against which model
   version, at what time. The product's entire claim is that a finding is traceable to its
   authority; a document that cannot be traced to its own run undercuts that at the last step.

2. **The Persian file still carries English fragments.** `cardinality` renders as `required` on the
   matched line, and `entity.detail` is `ifctester`'s English sentence. This is exact parity with
   the screen — the same fragments appear there — and T-0032 was explicitly forbidden from
   inventing presentation rules the view lacks, so the builder was right to leave them.

   But the stakes are different for the file. On screen, an English fragment in a Persian UI is a
   rough edge. In a document forwarded to a client or a plan reviewer, it is the sentence explaining
   *why* an element failed, unreadable to the person the report is for.

   `entity.detail` comes from upstream `ifctester` and is not ours to translate — **check whether
   upstream renders it translatably before writing anything** (`CLAUDE.md`: inherit before writing).
   `cardinality` is a payload value we already control, and T-0036 already queued the same defect on
   the screen — settle it in one place for both renderers, consistent with T-0052.

## Scope

**Changes**

- The file identifies itself: the run, the check date, and the engine version that judged it, in
  the body. `docs/decisions.md` already settled that engine version answers *"would this be judged
  the same way today"* — that is exactly the question a reader of an archived report has.
- The Persian file stops carrying English where the wording is ours to supply. Where it is not ours
  — upstream's detail sentence — the honest options are to inherit a translated form if upstream
  offers one, or to state plainly that the detail is upstream's words. Do not machine-translate a
  sentence whose precision is the point.

**What explicitly does not change**

- The presentation rules the view defines, except where this task deliberately settles a fragment
  for both renderers at once.
- The engine's own reason codes and labels, which already localize correctly.

## How to prove it ran

`make verify`, then a real generated file in both languages, pasted, showing the identifying block
and no English fragment whose wording we own. State explicitly what upstream `ifctester` does and
does not offer for `entity.detail`, with the check that established it.

## Evidence

## Review
