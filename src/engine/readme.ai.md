# readme.ai.md — src/engine/

## Purpose
The checking engine: the whole of `cadgpt-engine` (`docs/architecture/module-map.md`), the
distribution that carries the product's domain logic and must never resolve an inference
SDK (I1, I2 — enforced twice: by the dependency graph in `pyproject.toml`'s `engine` group,
which is what makes the isolation proof, gate 4, a fact about a real environment rather than
a policy; and by the import contracts gate 3 will add at C1.1, `docs/ddd/05-import-contracts.md`).

`src/engine/` itself is a container, nothing more. It holds the engine's bounded contexts as
sibling sub-packages — `ingest`, `observation`, `derivation`, `packs`, `resolution`,
`evaluation`, `findings` (`docs/architecture/module-map.md`) — and owns no logic of its own.
Today only `observation` exists; the rest are created by the task that first needs each one
(`CLAUDE.md` §6, no scaffolding).

It is **not** a place to put code that does not yet have a home. Anything that would live
directly under `src/engine/` rather than inside one of its named contexts is misplaced.

## Context
Spans every one of the engine's bounded contexts (`docs/ddd/03-bounded-contexts.md`); this
directory is the container, not any one of them. Subdomain: **core** — the engine is the
product's checking capability, the reason the rest of the system exists.

## Contract
`engine` exports nothing at this level. `__all__` is `[]`. Each context beneath it —
`engine.observation` today — is its own public surface, documented in its own
`readme.ai.md`. A caller imports `engine.<context>...`, never anything from `engine`
itself beyond the fact that it is importable.

## Invariants enforced here
None directly — `src/engine/` owns no domain aggregate itself; each context beneath it owns
its own (see that context's `readme.ai.md`).

I1 and I2 are the invariant this whole package exists to make true as a fact of the
environment: an `import` of an inference SDK or an HTTP client from anywhere under
`src/engine/` must be unresolvable, not merely disallowed. That fact is established by
`pyproject.toml`'s `engine` dependency group (no inference SDK, no HTTP client declared) and
proven by gate 4 (`tools/gates/isolation.py`) — this directory does not re-prove it, it is
what gate 4 is a fact about.

## Depends on
Nothing of its own. `__init__.py` imports only what makes the package exist. Its
sub-packages depend on the standard library and, per `docs/architecture/module-map.md`'s
dependency table, `ifcopenshell`, `ifcpatch`, `ifctester`, `topologicpy`, `shapely`,
`pydantic` — declared in the `engine` group of `pyproject.toml`, never here.

## Must not depend on
- **Any inference client or model SDK** (I1) — the reason this distribution exists as its
  own dependency group.
- **Any HTTP client outside `ifctester`'s own forced, allowlisted closure** (I2, DEC-0023) —
  gate 4 asserts the allowlist; `src/engine` itself must never import one directly.
- **`src/presentation`, `src/codification`, `src/assistance`, `src/connector`, `src/api`.**
  The layering in `docs/architecture/module-map.md` runs downward from `presentation`
  through `engine`'s own contexts to `ingest`; nothing above `engine` may be reached from
  inside it.

## Tests
None at this level — `src/engine/` has no logic of its own to test. Each context's tests
live beside that context (`src/engine/observation/tests/`, per `docs/architecture/module-map.md`).

## How to run it
```
$ uv run --group dev python -c "import engine; print(engine.__all__)"
[]
```
The package's only job is to exist and be importable; `engine.observation` is where the
real behaviour is (see its own `readme.ai.md`).

## Open questions
None.
