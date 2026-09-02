# T-0031 — Choosing which rules to run, recorded so the run stays reproducible

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** tenancy. **Reviewer-gated.**

## Why

The MVP is one sentence: *the user uploads a model, **picks which rules to run it against**, and
gets back a report file.* T-0030 builds the catalogue. This is the middle clause, and without it
the catalogue is a table nobody can reach.

The requirement that shapes this task is not the picking — it is the **recording**. `RuleSet`'s
own module docstring already states the principle for uploaded rules: *a stored rule set is what
makes a run reproducible from its inputs.* `prd.md` §5.7 extends it — every finding carries the
pack identity and version, because a finding asserts that a rule says something, under our name.
A run that records "checked against the catalogue" and not *which packs at which versions* is a
run nobody can re-derive, defend, or compare against a later one. The catalogue will change; the
record of what a given run actually checked must not.

## Scope

**Changes**

- The check-run record gains the selection: which packs, at which versions, were run. Store what
  is needed to reconstruct the run, not a foreign key that a later catalogue edit can silently
  redefine underneath it — a version string or a content hash captured **at dispatch time**.
  Follow how the existing run already records its inputs rather than inventing a second idiom.
- A migration.
- The API accepting a selection when a check is requested, validating it against the catalogue,
  and refusing an unknown or ambiguous pack rather than quietly running a subset. **Silently
  running fewer rules than asked for is the coverage failure this product exists to refuse.**
- The existing single-`RuleSet` path keeps working unchanged. A run cites either an uploaded
  rule set or a catalogue selection; both are legitimate.
- `services/web` — the selection surface, filterable by jurisdiction, region and version, and
  the run's recorded selection shown on the report.
- Both i18n catalogues.

**What explicitly does not change**

- The engine. It already takes IDS files; how they were chosen is not its concern, and
  `packages/engine` must not learn what a `RulePack` is. The import contracts will catch this.
- The catalogue model itself (T-0030) and the Markdown report (T-0032).
- Coverage, the counts, the three-valued discipline.

**One thing to get right.** A selection of several packs means several IDS files against one
model. Decide deliberately whether that is one run with several rule sources or several runs,
say which in the evidence, and make the report's coverage sentence still true under it —
"N of M specifications evaluated" must count across the whole selection, not per pack, or it
resumes claiming full coverage of whichever pack happened to be last.

## How to prove it ran

`make verify` with the 5 import contracts kept, then the real path against the running stack:

```sh
make up
# a real check, selecting from the catalogue, over HTTP
```

Evidence must show:

1. A real HTTP request creating a run with a catalogue selection, and the run record afterwards
   showing exactly which packs and versions it cites — pasted from the API response.
2. The check actually executing against those rules — the worker log line and the resulting
   counts, not just a 202.
3. **A refused selection**: an unknown or ambiguous pack rejected with a named reason, not
   silently dropped. Paste the response.
4. **Reproducibility**: change the catalogue after a run (bump a pack's version, or add one) and
   show the completed run still reports what it originally checked.
5. Tenancy: a run's selection is visible to its own tenant and not to another.
6. **Wiring**: the migration at head, the route quoted from the router, and the serializer field
   that carries the selection.

## Evidence

<!-- the builder writes this -->

## Review
