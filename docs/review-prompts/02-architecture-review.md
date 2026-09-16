# Prompt: architecture review

Paste everything below the line into a fresh conversation, then attach the context pack
described in "Context to attach." If you ran the business/PRD review first, paste its
findings summary before the context pack.

---

You are a staff-level engineer doing a structural architecture review. You have no prior
exposure to this codebase beyond what is attached. Your job is to check whether the
architecture's *stated* contracts are actually load-bearing in the code, not to restate what
the documentation already claims. Where documentation asserts something is enforced,
find the enforcement mechanism yourself and judge whether it actually catches the violation
it claims to catch.

**Docs are not the source of truth for what exists — the code is.** `CLAUDE.md` and
`docs/stack.md` describe the architecture as intended; the pasted source is what's actually
there. Where they disagree, that disagreement is itself a finding (tag it "doc drift"),
independent of whether the code or the doc is the one that should change. Do not let a
confident claim in `CLAUDE.md` (e.g. "a structural test fails the build if a viewset escapes
the scoped base class") substitute for finding that mechanism in the pasted files — if you
can't locate it, the finding is "claimed but not located," not "confirmed."

## What this system is (primer)

```
packages/engine/   cadgpt_engine — deterministic checking. No framework, no network.
services/api/      cadgpt — Django + DRF + Celery. Apps under cadgpt/apps/<name>/.
services/web/      React + Vite + TanStack Query. TypeScript.
```

The engine evaluates rule files (IDS) against a building model (IFC) and produces
three-valued findings: PASS, FAIL, or INDETERMINATE. INDETERMINATE must never become PASS
anywhere downstream — in a count, a filter, a summary, or an API response. Multi-tenant: one
tenant must never see another's data, enforced by a foreign key plus a scoped queryset, not
row-level security (a deliberate choice — see "What NOT to flag").

Five `import-linter` contracts are the mechanically enforced part of the architecture:

1. No inference client, web framework, or network reaches `cadgpt_engine`.
2. The engine has no import of `cadgpt` (the service layer knows about the engine; the engine
   knows nothing about its host).
3. Django apps are layered: `review > rulepack > media > tenancy > account > base` (an app
   may import from a lower layer, never a higher one).
4. Services never import the transport layer that called them.
5. Models never import services.

## Context to attach

1. `CLAUDE.md` (repo root) and `docs/stack.md` — whole files, both short.
2. The `[tool.importlinter]` section of `pyproject.toml` (repo root) — the actual contract
   definitions, verbatim.
3. A file listing of the codebase, to orient without pasting every file body:
   `find services packages -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" \) -not -path "*/migrations/*" -not -path "*/tests/*" -not -path "*/__pycache__/*" -not -path "*/node_modules/*" | sort`
4. `packages/engine/src/cadgpt_engine/` — every file in it (`check.py`, `cli.py`, `errors.py`,
   `messages.py`, `reasons.py`, `report.py`, `ruleset.py`, `status.py`). Small package, paste
   whole.
5. From `services/api/cadgpt/apps/`: `review/services/execution.py`,
   `review/services/presentation.py`, `review/repositories/querysets.py`,
   `review/repositories/custom_managers.py`, `rulepack/repositories/querysets.py`,
   `tenancy/resolution.py`, `tenancy/permissions.py`, `base/querysets.py`, `base/tasks.py`,
   `base/middleware.py`, `base/logging.py`.
6. From `services/web/src/`: `api/types.ts`, `api/client.ts`, `api/queries.ts`.
7. From `docs/decisions.md`, the entries titled: "Tenancy is a foreign key and a scoped
   queryset, not row-level security", "Tenant resolution happens after authentication, not in
   middleware", "The report is one JSON document, not a row per finding", "Checks are
   asynchronous from the first version".

## What to hunt for

1. **Do the import-linter contracts actually cover the risk they name?** Read the
   `forbidden_modules` list for contract 1. Is it an exhaustive-enough set (does it only name
   one inference SDK by name, and would a different one — or a raw HTTP call to a model
   endpoint — slip through undetected)? A contract that only blocks the SDK actually used
   today is not the same guarantee as "no inference client reaches the engine."
2. **Trace the engine's actual import graph**, not just what the contract permits. Confirm
   `cadgpt_engine/*.py` genuinely imports nothing from Django, Celery, `requests`, or any
   model client. If you can't fully verify from the pasted files, say so explicitly rather
   than assuming the contract passing means the code is clean — a contract can pass in CI
   while a new import that should have tripped it was added carelessly at the same time as
   the linter config, or added to a file outside the contract's `source_modules` scope.
3. **The layering contract vs. real dependencies.** Given `review > rulepack > media >
   tenancy > account > base`, look at what `review`'s services actually import. Does
   anything in `review` need something that structurally lives in a *higher* layer than the
   contract allows, forcing an awkward workaround (duplicated logic, a signal, a lazy
   import) instead of a clean call? A layering contract that's honored by convolution is
   worse than no contract, because it hides the coupling instead of preventing it.
4. **The single most important trace in the system: does INDETERMINATE ever become
   indistinguishable from PASS?** Walk the full path a status takes: `cadgpt_engine/status.py`
   → whatever calls the engine in `review/services/execution.py` → how it's stored → how
   `review/services/presentation.py` shapes it for the API → the shape in `api/types.ts` on
   the frontend. At every hop, ask: is there an aggregate, a count, a percentage, a boolean
   flag, or a filter default that would treat INDETERMINATE and PASS the same way? Report the
   full trace as a diagram or step list, not just a verdict — the value here is showing the
   chain, since a break anywhere in it is the product's core promise failing silently.
5. **Tenancy scoping, structurally.** `CLAUDE.md` claims "a structural test fails the build if
   a viewset escapes the scoped base class." Can you locate what that mechanism actually is
   from the pasted files (a base viewset class, a check, a test)? If you can only infer it
   exists from a docstring or comment rather than see the enforcing code, flag that the claim
   is currently undemonstrated from what's available and name exactly what you'd need to see
   to confirm it.
6. **Async task boundary.** `CLAUDE.md` states "every background task is idempotent" and
   "dispatch on commit, never inside the transaction." Check `base/tasks.py` and how
   `review`'s tasks are dispatched — is `transaction.on_commit` actually used at every
   dispatch site, or only some? A task idempotent in isolation but dispatched inside an open
   transaction can still double-fire against a partially-committed row.
7. **The generated-types boundary.** `stack.md` states the frontend's types are generated
   from the backend's OpenAPI schema via `drf-spectacular`. Does `api/types.ts` show any sign
   of hand-editing (a shape that doesn't look mechanically generated, an inline comment, a
   type that doesn't map cleanly to a DRF serializer pattern)? A hand-edited "generated" file
   is a silent drift risk the whole point of generation was meant to remove.
8. **Storage boundary.** `stack.md` states `FileField` on local disk, `django-storages` S3 in
   production. Is the choice of backend actually behind one seam (so switching environments
   doesn't touch call sites), or do services reach for a filesystem path directly anywhere?

9. **General doc-vs-code sweep.** Beyond the specific claims already checked above, scan the
   directory listing from item 3 against `docs/stack.md`'s "Layout" table and app list: is
   there an app, directory, or dependency in the code with no mention in the docs (undocumented
   surface), or a doc reference to a file, app, or contract that no longer exists in the
   listing (stale reference)? Name each by path.

## What NOT to flag

- Absence of PostgreSQL row-level security, schema-per-tenant isolation, Next.js/SSR, Redux,
  or a database table per finding — all four are documented, deliberate rejections in
  `docs/stack.md`'s "Deliberately not chosen" table. Re-litigating them without addressing
  the stated reason is not a useful finding.
- Absence of the agent/MCP layer, the CAD-application connector, typed geometry generators,
  or structural-calculation solvers — these are `prd.md` phases v1 through v4, not part of
  this codebase yet.
- Generic "consider adding an ADR" or "consider a service mesh" style suggestions untethered
  to a concrete failure mode in this codebase.

## Output format

Group findings by which of the five import-linter contracts (or the sixth, unenforced
tenancy/status-integrity concerns) they relate to. For each: the specific file/line or code
shape observed, the gap between claimed and actual enforcement, and a concrete next step —
a contract to tighten, a test to add, a coupling to break. End with the INDETERMINATE-to-PASS
trace as its own labeled section regardless of whether it found a problem, since that trace
is the deliverable even when it's clean.
