# CLAUDE.md

`prd.md` is the product source of truth. This file is the engineering rules. Both are short
on purpose. Decisions go in `docs/decisions.md`; the route is `docs/plan.md`; what we use
and why is `docs/stack.md`; how the build itself is run is `docs/agents.md`.

## What we are building

A multi-tenant web app: a design office uploads an IFC model and an IDS rule file and gets a
report of what passes, what fails, and what could not be determined. The rules are data —
the app is jurisdiction-agnostic and ships with no building code baked in.

## Invariants

These are the ones that survived contact with reality. Do not trade them away.

- **The model never evaluates a rule.** Rule evaluation is deterministic code. An LLM may
  help author rules or explain results; it never decides pass or fail. Enforced by an import
  contract, not by memory.
- **The model never authors geometry freehand.**
- **Measure, never invent.** Computing a quantity from geometry the designer authored is
  measurement. Synthesising a space, boundary, or classification they did not author is
  invention. Missing input is reported as missing, never filled in.
- **Three-valued, always.** `PASS | FAIL | INDETERMINATE`. `INDETERMINATE` never becomes
  `PASS` in any count, summary, filter, or API response. This is the product's whole
  value-add over raw `ifctester` — see `docs/decisions.md`.
- **Never assert compliance we did not establish.** Say what was checked and what was not.
- **One tenant never sees another's model.** Every tenant-owned table carries `tenant`, every
  read goes through `for_tenant`, and a structural test fails the build if a viewset escapes
  the scoped base class. There is no row-level security behind it.

## Layout

```
packages/engine/   cadgpt_engine — deterministic checking. No framework, no network.
services/api/      cadgpt — Django + DRF + Celery. Apps under cadgpt/apps/<name>/.
services/web/      React + Vite + TanStack Query. TypeScript, RTL-native.
deploy/            Dockerfiles and the compose stack.
```

## Rules

- **Inherit before writing.** `ifcopenshell`, `ifctester`, and their reporters do the
  parsing, evaluation, and report generation. Before writing anything in that space, check
  whether it already exists upstream. Replacing our code with an inherited component is
  always the preferred direction.
- **The boundaries are contracts, not conventions.** Five `import-linter` contracts in
  `pyproject.toml` enforce the engine's isolation, the app layering, and the direction of
  the service and model dependencies. If a change wants to violate one, the change is
  usually in the wrong place — moving the code is the fix, not exempting the import.
- **Business logic lives in a service.** Not in a serializer, which only exists in a request;
  not in a model, which must stay callable during a migration; not in a view, which a worker
  cannot reach. Query logic lives in a queryset. Managers are thin and only write.
- Types at module boundaries. `mypy --strict` passes.
- No placeholders, no `TODO`, no scaffolding. Do not create a file, package, abstraction, or
  config option before something needs it.
- Fix root causes. Never silence a warning or swallow an exception to make output clean.
- **Every user-facing string goes through `gettext`.** The tenants are multinational; the
  engine names reasons with codes and the service supplies the wording.
- **Every background task is idempotent.** `acks_late` means a message survives a dead worker
  and will be delivered again. Dispatch on commit, never inside the transaction.
- Tests run the real path: a real IFC, a real IDS, real output. Mock only a paid external
  API. Fixtures are small real files or a script that generates them.
- **Done means it ran.** Before calling anything done, execute the real entry point over real
  input and show the output. A green test suite is not evidence — this repository has a
  documented history of suites passing while nothing worked, and the last three defects here
  were all found by running the stack, not by the tests.
- **The build runs as the loop in `docs/agents.md`.** A coordinator holds the plan and writes
  no production code; a builder takes one task file and must prove the real path ran; a
  reviewer is gated on invariants and milestones, returns findings only, and is never
  dispatched twice on the same task. Every task is a file under `docs/tasks/`, written before
  the work starts and carrying the evidence after.
- When a decision is settled, append a paragraph to `docs/decisions.md` so it survives
  context loss. When something is genuinely a direction question — two answers give two
  different products — ask. Otherwise decide and log it.

## Verify

```sh
make verify     # ruff, mypy --strict, import contracts, pytest, frontend build
make up         # the whole stack, to run the real path against
```
