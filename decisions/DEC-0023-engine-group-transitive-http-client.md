# DEC-0023 — What "the engine distribution has no HTTP client" means when an inherited component brings one

**Status:** DECIDED
**Date:** 2026-08-30
**Raised by:** Subagent, T-0001 — found while declaring the dependency groups in `pyproject.toml`
**Decided by:** Lead
**Affects:** `pyproject.toml`, `docs/architecture/harness.md`, `docs/architecture/module-map.md`, T-0003 (isolation proof, gate 4), I1

## Problem
`docs/architecture/module-map.md` says `cadgpt-engine` may depend on ifcopenshell, ifcpatch,
ifctester, topologicpy, shapely and pydantic, and carries **no inference SDK and no HTTP client**.
Declared exactly so, the group resolves an HTTP client anyway:

```
$ uv tree --depth 3
ifctester v0.8.5
├── bcf-client v0.8.5
│   └── requests v2.34.2
└── flask v3.1.3

$ uv export --no-hashes | grep -Ei '^(openai|anthropic|httpx|requests|urllib3|flask|bcf-client)\b'
bcf-client==0.8.5
flask==3.1.3
requests==2.34.2
urllib3==2.7.0
```

Reproduced independently by the Lead. No inference SDK appears; `httpx` and `aiohttp` do not
appear. `requests` and `flask` arrive through `ifctester`, a **forced inherited component**
(`prd.md` §5.6, I3).

So `harness.md`'s claim that gate 4 closes "a raw HTTP call to an inference endpoint" is false as
stated: `requests` is importable in the engine environment and cannot be removed without
breaking an inherited component.

## Constraints
- I1 must be a **fact**, not a policy (DEC-0004). That is why gate 4 exists apart from gate 3.
- I3 and `prd.md` §5.6: `ifctester` is inherited, not forked, not replaced, not resolver-overridden
  into an environment its own test suite never ran in. **Settled.**
- DEC-0004's own text is the declared-set reading: the engine "declares no inference SDK and no
  HTTP client", and CI "asserts that importing one" — an inference SDK — "raises `ImportError`".
- DEC-0004's Reopens is "Never for the engine". This record does not reopen it; it says what its
  words mean where an inherited component makes them ambiguous.

## Options
1. **Declared-set only.** Gate 4 probes for inference SDKs; the raw-HTTP path stays open and
   unremarked, and the closure may silently grow `httpx` tomorrow with nothing noticing.
2. **Resolved-set purity.** Prune `requests`/`flask`. Requires overriding `ifctester`'s hard
   dependency, moving `engine/evaluation` out of the engine distribution, or replacing
   `ifctester` — each contradicts a settled decision (I3, `prd.md` §5.6, `module-map.md`).
3. **Declared-set purity, plus a ratchet on the resolved set, plus a static contract on the
   written code.**

## Decision
**Option 3.** The constraint is enforced in three places, each doing what it can actually do:

1. **Declaration.** `cadgpt-engine` declares no inference SDK and no HTTP client. Unchanged.
2. **Gate 4 (resolved environment).** Asserts that (a) no inference SDK resolves in the engine
   environment — `import` of each raises `ImportError`; and (b) every HTTP-capable package in the
   engine closure appears in an allowlist committed beside the gate, **as a `(package, reached_via)`
   pair**. Today that allowlist is exactly `requests`, `urllib3`, `flask`, `bcf-client`, each
   `reached_via` `ifctester`. A new HTTP-capable package, or an existing one arriving by a new
   path, fails the gate. The closure cannot grow an HTTP client silently.
3. **Gate 3 (import contracts).** No module under `src/engine` may import an HTTP client or a
   socket module — `requests`, `urllib3`, `httpx`, `aiohttp`, `http.client`, `urllib.request`,
   `socket`. This is what actually closes the raw-HTTP path, and it ships with gate 3 at C1.1,
   when `src/engine` first exists.

Reading B is not chosen because its every lever contradicts a settled decision. Two readings do
not here produce two admissible products, so this is a Lead decision and not a stakeholder
question (`CLAUDE.md` §0).

## Expected result
An inference SDK is unresolvable in the engine environment — a fact, unchanged. A raw HTTP call
from engine code is statically unwritable once gate 3 ships, and until then no engine code exists
to write it in. The presence of `requests` is recorded, attributed to the component that forces
it, and cannot grow.

## Reopens if
`ifctester` drops `bcf-client`, or the engine's `ifctester` wrapper moves to its own distribution
— either makes the allowlist empty and Option 2 free, at which point take it. Also reopens if any
inference provider ships an SDK-free HTTP-only interface we intend to call, which would make an
allowlisted HTTP client a live I1 risk rather than a recorded one.

## Consequences accepted
Gate 4 is weaker than `harness.md` claimed: between now and C1.1 the raw-HTTP path is closed by
nothing, and it is closed by a static contract thereafter, which `importlib` can defeat in
principle. Accepted, because the alternative is forking an inherited component to close a path
that no code can currently take. `harness.md` and `module-map.md` are corrected to say this
rather than overclaim it.
