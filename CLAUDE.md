# CLAUDE.md

`prd.md` is the product source of truth. This file is the engineering rules. Both are short
on purpose. Decisions go in `docs/decisions.md`; the route to the MVP is `docs/plan.md`.

## What we are building

A web app: upload an IFC model and an IDS rule file, get a report of what passes, what fails,
and what could not be determined. The rules are data — the app is jurisdiction-agnostic and
ships with no building code baked in.

## Invariants

These are the ones that survived contact with reality. Do not trade them away.

- **The model never evaluates a rule.** Rule evaluation is deterministic code. An LLM may help
  author rules or explain results; it never decides pass or fail. Enforced by an import
  contract, not by memory.
- **The model never authors geometry freehand.**
- **Measure, never invent.** Computing a quantity from geometry the designer authored is
  measurement. Synthesising a space, boundary, or classification they did not author is
  invention. Missing input is reported as missing, never filled in.
- **Three-valued, always.** `PASS | FAIL | INDETERMINATE`. `INDETERMINATE` never becomes `PASS`
  in any count, summary, or API response. This is the product's whole value-add over raw
  `ifctester`, which reports "attribute is missing" and "attribute violates the rule" both as
  `FAIL` — see `docs/decisions.md`.
- **Never assert compliance we did not establish.** Say what was checked and what was not.

## Rules

- **Inherit before writing.** `ifcopenshell`, `ifctester`, and their reporters do the parsing,
  evaluation, and report generation. Before writing anything in that space, check whether it
  already exists upstream. Replacing our code with an inherited component is always the
  preferred direction.
- Types at module boundaries. `mypy --strict` passes.
- No placeholders, no `TODO`, no scaffolding. Do not create a file, package, abstraction, or
  config option before something needs it.
- Fix root causes. Never silence a warning or swallow an exception to make output clean.
- Tests run the real path: a real IFC, a real IDS, real output. Mock only a paid external API.
  Fixtures are small real files or a script that generates them.
- **Done means it ran.** Before calling anything done, execute the real entry point over real
  input and show the output. A green test suite is not evidence — this repository has a
  documented history of suites passing while nothing worked.
- When a decision is settled, append a paragraph to `docs/decisions.md` so it survives context
  loss. When something is genuinely a direction question — two answers give two different
  products — ask. Otherwise decide and log it.

## Verify

```sh
make verify     # ruff, mypy --strict, pytest, import contract
```
