# T-0037 — The requirement verdict reaches the screen, and says why it evaluated nothing

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** three-valued results, I5, I7. **Reviewer-gated.** It changes the wire
format and it changes what the architect reads first.

## Why

Both halves found by the T-0028 review.

**T-0028's fix is currently invisible.** `requirement.status` is produced by the engine, stored
in `CheckRun.report`, serialised by `CheckRunDetailSerializer`, typed at
`services/web/src/api/types.ts:74` — and read by nobody. `ReportView.tsx` mounts `StatusPill`
in exactly three places: line 102 (`report.status`), line 170 (`spec.status`), line 193
(`entity.status`). A requirement is rendered at line 182 as
`<p className="requirement__description">{requirement.description}</p>` and nothing else. So
the verdict T-0028 corrected — a requirement that evaluated nothing no longer claiming PASS —
does not exist on the surface the architect actually reads. It is real in the CLI `--json` and
in the HTTP response only. Dead data end to end.

**And a bare status would not be enough.** Rendering it alone produces a prohibited
specification judged `PASS` at the specification level, correctly, with an `INDETERMINATE`
requirement row beneath it. Reproduced by the reviewer: an IDS with `minOccurs="0"
maxOccurs="0"` over `IFCWINDOW` against `three_doors.ifc`, which contains only `IfcDoor`, gives

```
SPEC APPLIES PASS prohibited matched 0 NO_SUBJECTS_AND_PROHIBITED
   REQ INDETERMINATE | p/f/i 0 0 0 | "The Name shall not be provided"
```

Both lines are true and they look like they disagree. `docs/decisions.md`, *"A requirement that
evaluated nothing is explained, never suppressed"*, settles the direction: **the row stays and
is made to explain itself.** Suppressing it would make the report look cleaner by deleting the
sentence that tells the truth about coverage, which is the failure I7 exists to close. Do not
re-open that decision.

## Scope

**Changes**

- `packages/engine/src/cadgpt_engine/report.py` — `RequirementOutcome` gains a `reason_code`
  field, nullable, carrying why the requirement evaluated nothing. This is a wire format
  change: **bump `REPORT_SCHEMA_VERSION`.**
- `packages/engine/src/cadgpt_engine/check.py` — populate it. The reason already exists one
  level up (`NO_SUBJECTS_AND_PROHIBITED`, `NO_SUBJECTS_NOTHING_CHECKED`); read `status.py`'s
  `ReasonCode` list and reuse rather than adding a synonym. A requirement that genuinely
  evaluated entities carries `None`.
- `services/api/cadgpt/apps/review/services/presentation.py` — the code gets its wording here,
  not in the engine. `CLAUDE.md`: the engine names reasons with codes and the service supplies
  the wording, through `gettext`.
- `services/web/src/api/types.ts`, `services/web/src/components/ReportView.tsx` — a
  `StatusPill` beside `requirement.description`, and the reason rendered when present.
- Both i18n catalogues. `services/web/e2e/report.spec.ts`.

**Does not change:** `judge()`, the specification-level reasoning, `_aggregate` (T-0028 is
settled), and the three entity counts. Do not suppress any row.

## How to prove it ran

Commit the prohibited-matching-nothing IDS the reviewer constructed as a real fixture — the
existing fixtures cannot reach this state, which is why the defect was invisible.

```sh
uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc <the new fixture> --json
make verify
make up   # rebuild web: docker compose -f deploy/compose.yaml up -d --build web
make e2e
```

Evidence must show, from the rendered page in a real browser: the requirement row carrying
`INDETERMINATE`, and the reason rendered beside it in words rather than as a code. Plus the
`REPORT_SCHEMA_VERSION` before and after, and a mutation proof on the new e2e assertion.

## Evidence

<!-- the builder writes this -->

## Review
