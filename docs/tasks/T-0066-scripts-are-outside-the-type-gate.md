# T-0066 — `scripts/` is outside the type gate

**Phase:** 3   **Status:** open
**Touches invariants:** types at module boundaries.

## Why

Found by the T-0033 review. `make types` runs `mypy` over `packages/engine/src services/api/cadgpt`
only, so the two scripts T-0033 committed — `scripts/measure_check_memory.py` and
`scripts/generate_large_ifc_model.py` — are not under `mypy --strict`, despite `CLAUDE.md` requiring
types at module boundaries and `make verify` being the gate that is supposed to enforce it.

They are committed, they produce a number that is now written into a settings constant and a decision
record, and nothing type-checks them. `pyproject.toml` also gained `"scripts/*.py" = ["T20"]` — a
real diff line the task file's "Files touched" list omits.

Recorded and **not treated as a defect**: `deploy/compose.yaml` runs
`DJANGO_SETTINGS_MODULE: cadgpt.config.settings.local`, so the 4GiB denominator underpinning the
ceiling is a declared value in the *development* stack, and no production deploy artifact exists in
the repository. Given there is no production target to measure, that is the best denominator
available, and both `base.py` and `docs/decisions.md` already state the number reopens if it changes.
It is noted here so that whoever writes the production deploy knows the ceiling depends on it.

## Scope

- `scripts/` comes under the same type gate as the rest of the repository, or the gate's exclusion of
  it is deliberate and written down.
- The `pyproject.toml` lint exemption is either justified in place or removed.

**What explicitly does not change** — the scripts' behaviour, or the measurement they produce.

## How to prove it ran

`make verify` with the scripts type-checked, and a deliberate type error in one of them shown failing
the gate. A gate that does not fail is not a gate.

## Evidence

## Review
