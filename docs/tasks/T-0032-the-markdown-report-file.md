# T-0032 — The report as a file, and its URL on the job record

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** I7, three-valued results, tenancy. **Reviewer-gated.**

## Why

This is the MVP's last clause and the thing the whole loop has been building toward: *the user
uploads a model, picks which rules to run it against, and **gets back a report file**.*

Settled 2026-09-02 (`docs/decisions.md`, `prd.md` §12): the deliverable is a **generated
Markdown report** whose URL sits on the job record. Markdown because it survives the tooling,
renders where the office already works, and needs no layout engine. The in-app React view stays
**beside** it, not under it — this task does not replace the view and must not degrade it.

Everything this file has to say has already been built and reviewed. The file is not a new
report; it is the report we already produce, in the form that leaves the building:

- the **disclosure** (T-0029) — what was checked, the model and not the drawing set;
- **coverage before findings** (T-0025), with the numerator that is a real measurement and not
  `N of N`, and the specifications that established nothing named rather than counted;
- **severity ordering** FAIL → INDETERMINATE → PASS (T-0025);
- the **requirement as a localized citation** with its subject (T-0027);
- the three counts, all three, always (I3).

## The decision this task inherits

`docs/decisions.md`, *"Report prose belongs to the server, not to the frontend catalogue"* —
written because of this task. **Every string in the generated file is authored on the server**,
through `gettext`, and the disclosure specifically comes from `cadgpt.apps.review.disclosure`,
which already exists and which the React view already renders from. Do not retype a sentence
that module owns; do not build a second catalogue. If you find yourself needing a string the
server does not have, add it beside the existing ones rather than inlining it in a template.

The presentation rules `ReportView.tsx` implements are the **specification** for this generator
(`docs/plan.md`). Where the file and the view disagree about ordering, coverage arithmetic, or
what is named, the file is wrong.

## Scope

**Changes**

- A generator in `services/api/cadgpt/apps/review/` producing Markdown from a stored report.
  Business logic in a service. It takes the localized report — the same `localize_report` output
  the API serves — so wording and rendering stay one path, not two.
- The **language** of the file is a real decision: a run belongs to a tenant, the file is
  generated once, and Markdown carries no locale negotiation. Decide deliberately whose language
  the file is written in, implement it, and **state the choice and its reasoning in the
  evidence**. If it is the tenant's configured language, say what happens when that changes
  after the file was written.
- The file is stored through the existing `media` app rather than a new storage path, under the
  tenant's prefix, and its URL goes on the job record. **One tenant never sees another's file** —
  this is the tenancy invariant and it applies to a generated artifact exactly as to an upload.
- Generation is dispatched **on commit, never inside the transaction**, and the task is
  **idempotent** — `acks_late` means the message survives a dead worker and will be delivered
  again. Re-running must not produce a second file or a half-written one.
- `services/web` — surface the link on the run.
- Tests, including a real one that reads the generated file's bytes.

**What explicitly does not change**

- The engine, the report schema, the counts, the view. This task reads what exists.
- No PDF, no HTML export, no overlay, no marked sheets, no BCF — out of the MVP by decision.
- No new presentation rules. If the file needs a rule the view does not have, that is a finding
  about the view, not licence to invent one here.

## How to prove it ran

`make verify` with the 5 import contracts kept, then the real path end to end on the running
stack — upload, check, and fetch the file:

```sh
make up
# a real run, then GET the report URL off the job record
```

Evidence must show:

1. **The generated file itself, pasted whole**, for the `three_doors.ifc` / `door_width.ids` run.
   It must contain the disclosure, coverage before findings, the three counts, and the FAIL row
   ordered above the INDETERMINATE row. Paste the raw Markdown, not a rendering of it.
2. The same file **in the other language**, proving the wording came from the server's catalogue
   and not from a template's hardcoded English.
3. The URL on the job record, fetched over real HTTP, and the file downloaded from it.
4. **Idempotence**: run the generation task twice against the same run and show one file, not
   two — paste both invocations and the resulting file list.
5. **Tenancy**: a second tenant refused access to the first tenant's file. Paste the response.
6. **Wiring**: the Celery task registered (quote the registration), dispatch on commit (quote
   the line), the migration at head, and the route.
7. A mutation proof on the assertion that coverage precedes findings in the file.

## Evidence

<!-- the builder writes this -->

## Review
