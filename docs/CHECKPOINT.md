# Checkpoint — 2026-09-02, end of coordinator session 1

Written because the coordinator session was ended for context reasons mid-Phase-3. This file
is the handoff. `docs/plan.md` is still the route and `docs/tasks/` still holds the detail;
this only records where the loop was interrupted and what is unresolved.

## Where the loop stopped

Phase 3 is **in progress**. Three tasks landed, one is built but unreviewed, two are queued
and specified.

| Task | State | Commit |
|---|---|---|
| T-0024 — browser evidence harness | **done** | `c9d351f` |
| T-0026 — requirement description from `to_string` | **done**, reviewed, fix-now applied | `b38b15a` |
| T-0025 — report presentation | **built, review outstanding** | this checkpoint's commit |
| T-0027 — requirement as structured citation | open, specified | — |
| T-0028 — a requirement that evaluated nothing must not report PASS | open, specified | — |

Numbering continues at **T-0029**. T-0025 is out of numerical order because T-0026 was filed
from T-0024's evidence and sequenced ahead of it deliberately.

## The one unresolved thing

**T-0025's review never landed.** The reviewer was dispatched and was still running when the
session ended, so its findings are lost. Re-dispatch it — `docs/agents.md` forbids a *second*
review of a task, and this task has not had a first one. The task file lists exactly what it
was asked to hunt so the next dispatch does not re-derive it; the short version is that the
filter is the dangerous surface and only one of its states is covered by a test.

T-0025 was committed rather than held back because it passes every gate and its evidence was
independently verified by the coordinator — but it is **not done**, and Phase 3 must not be
marked complete until that review runs.

## What was decided in this session

Both are written into `docs/decisions.md` in full; they are named here so the next coordinator
knows they exist and does not re-litigate them.

- **A frontend change proves itself in a browser against the running stack.** Playwright, not
  jsdom. `make up` then `make e2e`. This was a user decision, not the agent's.
- **Severity, for a report built on IDS, is the three-valued status** — FAIL, INDETERMINATE,
  PASS. IDS carries no severity field and inventing one would be invention.

## What running the stack found that the suite did not

The pattern in `CLAUDE.md` held again, which is worth recording because it is the argument for
the whole loop:

- The T-0024 harness rendered its first report and the requirement line read
  `<ifctester.facet.Attribute object at 0x76f24ab599a0>` — in every report the product had
  ever produced. Became T-0026.
- T-0026's reviewer found that the fix *introduced* a regression: threading the real
  `Specification` activated an upstream early return, so a prohibited specification rendered
  "The requirement is not applicable" directly under a FAIL verdict.
- Two builders in a row wrote a test that passed with its own fix reverted, and one wrote an
  evidence claim that was impossible (`git stash` on an untracked file). Both were caught by
  review and by the coordinator re-running the mutation rather than accepting the claim.

**Do not take a builder's evidence block on trust.** Re-run the mutation. Open the screenshot.

## Environment notes that cost time to discover

- The `builder` and `reviewer` agent types in `.claude/agents/` are **not registered** as
  dispatchable agent types in this harness. Dispatch `general-purpose` instead and instruct it
  to read `.claude/agents/builder.md` or `reviewer.md` as its role contract. Builder on sonnet,
  reviewer on opus.
- The compose stack was left **up** at the end of this session. `docker compose -f
  deploy/compose.yaml ps` to confirm; `make up` rebuilds, which is required for a frontend
  change to reach the served container.
- `ruff format` no longer scans `docs/**` (`pyproject.toml`). It was rewriting quoted defects
  inside task files into different code. A code quote in a task file is evidence.
- `make verify` at this checkpoint: ruff clean, 151 files formatted, `mypy --strict` over 138
  source files, **5 import contracts kept**, **164 tests passed**.
