# T-0033 — The upload ceiling, measured against peak worker memory, and a run that exceeds it failing by name

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** none directly. **Reviewer-gated** — the queue-starvation half is a
whole-product availability property and the measurement is a claim about production behaviour,
which is exactly the shape of claim this repository has a history of getting wrong on paper.

## Why

`MAX_UPLOAD_BYTES` is `512 * 1024 * 1024` at `services/api/cadgpt/config/settings/base.py:151`.
Nothing measured it. It is a round number that looks generous, and the plan is explicit that
this is the wrong way to pick it: *"High enough to serve 95% of users, and derived from peak
worker memory rather than chosen as a round number."*

The reason it must be derived is the second half of this task. Async removed the *time*
constraint on a large model; it did not remove the *memory* one. The worker runs
`--concurrency 2` (`deploy/compose.yaml`) with no memory limit, `execute_check_run` is
`acks_late`, and `CheckRunExecutor._claim` deliberately re-claims a `RUNNING` run because the
only way it sees one is that the worker holding it died. That combination is correct for a
worker killed by a deploy and catastrophic for a worker killed by the OOM killer: the model
that exhausted memory is redelivered, claimed again, and exhausts memory again, forever, on a
shared queue. **One tenant's oversized model starves every other tenant's checks.** That is the
poison-message failure the plan names, and it is currently reachable by uploading a file the
API accepts.

So: measure what a check actually costs in memory, set the ceiling from the measurement, state
the ceiling to the user at upload time instead of at failure time, and make the run that
exceeds it terminate with a named reason rather than cycle.

## Scope

**Changes**

- **The measurement.** A repeatable script or management command that runs a real check over
  real models of increasing size and records **peak RSS of the process doing the work**, not
  wall time and not container memory at rest. It must cover at minimum the models this
  repository already has — the 2.3MB Duplex and the 47MB Schependomlaan named in Phase 0 — and
  at least one model materially larger than 47MB, generated if none is on hand. The output is a
  table of model size against peak RSS, and it lands **in this task file as evidence** and as a
  paragraph in `docs/decisions.md` stating the derived ceiling and the reasoning that produced
  it. The script is committed; a measurement nobody can re-run is an anecdote.

- **The ceiling, derived.** `MAX_UPLOAD_BYTES` becomes a number the measurement justifies,
  against the worker's real memory budget at `--concurrency 2` — two concurrent checks share
  one worker container, so the budget per check is not the whole container. Write the
  derivation down beside the constant: what was measured, what headroom was left, and what
  container memory the number assumes. A future reader must be able to see that the number
  would change if the concurrency or the container limit changed.

- **The worker's memory budget becomes explicit.** The compose worker has no memory limit
  today, so "peak worker memory" has no denominator and the OOM killer's threshold is the
  host's. Give the worker a declared limit consistent with the derivation. An unbounded worker
  makes the ceiling unfalsifiable.

- **The poison message stops cycling.** A run that dies from resource exhaustion must reach a
  terminal state with a named reason rather than being redelivered indefinitely. `_claim`'s
  re-claim of a `RUNNING` run is correct and stays; what must change is that a run cannot be
  claimed unboundedly many times. Add the bound, and add the reason to `CheckRunFailure` —
  which already models exactly this distinction: *"A rejected input and a crashed worker are
  different events with different remedies, and collapsing them into one 'failed' would leave
  the user with nothing to act on."* `STALLED` is not this reason; a stalled run stopped
  responding, and this one was ended on purpose because it cost too much.

- **The ceiling is stated at upload time.** `services/web` names the limit before the user
  picks a file, and the rejection message already in `MediaService._validate` reads in human
  units rather than as a raw byte count — `"larger than the 536870912 byte limit"` is a number
  no architect can act on. Both i18n catalogues.

**What explicitly does not change**

- `MAX_BYTES[IDS_RULESET]`. The 8MB rule-set cap is separately reasoned and correct.
- The engine. It is handed a path and measures a model; how large a file the product accepts
  is a product decision, and `packages/engine` must not learn the ceiling.
- `reap_stalled_runs`, which solves the different problem of a run whose worker vanished
  without the message coming back.
- Chunked or resumable upload, S3 multipart authorization, per-tenant quotas. Named as
  deliberately-not-built in `docs/plan.md` and still not built.
- The three-valued discipline: a run that could not be executed is a **failed run**, not an
  `INDETERMINATE` result. It has no report and produces no counts. Do not model resource
  exhaustion as a finding about the model.

**One thing to get right.** The bound on redelivery must distinguish *this run was tried too
many times* from *this run is being tried concurrently*, and it must survive the worker being
killed at any point — including between claiming the run and recording the claim. A counter
incremented after the expensive work begins is a counter an OOM kill never persists, which
leaves the cycle exactly as it was. Decide where the increment lands, say why in the evidence,
and prove it with a kill, not with an argument.

## How to prove it ran

`make verify` with the 5 import contracts kept, then the real path against the running stack:

```sh
make up
```

Evidence must show:

1. **The measurement table**, pasted: model size against peak RSS, at least three sizes
   including one above 47MB, produced by the committed script. State the command that produced
   it and the container the process ran in.
2. **The derivation**: the ceiling that follows from the table, the concurrency and container
   limit it assumes, and the headroom. A number without its denominator is not a measurement.
3. **A refused upload over HTTP**: a file above the new ceiling rejected, with the response
   pasted, in units a person can read.
4. **The poison message, killed rather than cycling.** Force a resource-exhausted run — a
   worker memory limit low enough that a real check dies under it is the honest way to do it —
   and paste the worker log across redeliveries showing the run reaching a terminal `FAILED`
   with the new named reason, and the queue continuing to serve a *second* run afterwards. The
   second run completing is the point: the claim is that one tenant no longer starves another.
5. **The ceiling stated before the failure**: a screenshot or the rendered text from
   `make e2e`'s chromium showing the limit named at upload time in both locales.
6. **Wiring**: the migration at head if the failure reason needs one, the setting quoted from
   `base.py` with its derivation comment, and the worker's declared memory limit quoted from
   `deploy/compose.yaml`.

## Evidence

<!-- the builder writes this -->

## Review
