# Aggregates and invariants

An aggregate is a consistency boundary: the smallest thing that must be correct all at
once. Each invariant below is enforced in exactly one place — its owning aggregate — and
nowhere else. Defensive re-checking downstream is forbidden; it hides which layer is
actually responsible.

Every invariant here is stated as a rule that can be *tested*, because each becomes a test
in the slice that builds it.

---

## `Observation` — value object

The atom. `(subject, property, convention) → value`, plus kind, provenance, confidence.

**Invariants**
- Immutable. An observation is never edited; a corrected measurement is a new observation.
- `property` name encodes its convention. A property name with no convention segment is rejected at construction.
- `kind ∈ {measured, related, derived}`. A `derived` observation carries a non-empty derivation trace naming the pack that produced it.
- A `measured` observation carries provenance and confidence.
- Equality and identity are the tuple. Two observations with the same tuple and different values are a **corroboration conflict**, which is a finding, not an error to resolve.

**Not an invariant:** that a value is correct. Nothing at this level can know that.

---

## `ObservationManifest` — value object

What a pack requires, versus what derivation produced.

**Invariants**
- Computable statically from the pack alone, before any model is loaded.
- `required − produced` is the INDETERMINATE set, computed by set difference, never by catching an exception.
- A rule requiring an observation type that **no registered derivation can produce** is a *build* error, not a runtime one. This is the single guard that stops a missing derivation from becoming a silent pass.

---

## `ClauseRecord` — entity, lifecycle `draft → ratified`

The authored unit of a rule. Owned by a `RulePack`.

**Invariants**
- Carries `text_src` verbatim in the original language and script. Never paraphrased, never translated in place.
- **Every encoded parameter stores the source quote it was taken from, beside it.** A parameter with no quote does not compile.
- The encoded value must agree with its quote under numeral and unit normalisation for the source script. Disagreement fails the build (quote linter). *This guard exists because a mistranscribed bound produces a cited, deterministic, reproducible, wrong PASS — the worst output the system can generate.*
- A `draft` has no ratifier and **cannot compile**. State transition to `ratified` requires a named person. Not a flag; a name.
- Declares: applicability predicate *and the facts that predicate depends on*; which of the four dates it keys on; compliance route; tolerance policy; severity.
- Has exactly one passing and one failing fixture. Neither may be authored by the same generator that authored the record.
- Contains no jurisdiction, country, code name or clause reference **in any identifier** (the text fields carry them; the names do not).

---

## `RulePack` — aggregate root

One code, standard, jurisdiction or firm checklist. The only place a jurisdiction exists.

**Invariants**
- Versioned against code cycles and effective dates.
- Compiled `.ids` is generated, never hand-edited. Regenerating from source must reproduce the committed artefact byte-for-byte, or the build fails (compile drift).
- Every compiled `.ids` passes IDS-Audit-tool.
- Every fixture runs in CI. A pack whose fixtures do not run is not shipped.
- No inference client executes inside a pack at check time.
- Readable and editable by a domain expert who is not a programmer. *This is the difference between this and a rule-checking tool that needs a consultant to configure, and it is testable: a non-programmer edits a bound and the pack recompiles.*
- Every derivation it depends on is declared, and each is either in the shared set or lives with its rule. Promotion to shared requires ≥3 rules across ≥2 clauses.

---

## `Adoption` — aggregate root

A jurisdiction's enactment: which packs, at which editions, with which overlays.

**Invariants**
- A dependency **closure**, not a single node. A clause may bind another standard at a named edition, and an adoption may amend that binding.
- Declares `conflict_policy` explicitly: most-restrictive, or explicit precedence. There is no default. *Fixed precedence is silently wrong whenever the stricter provision sits lower in it.*
- Under most-restrictive, both branches are evaluated and the finding records which governed and why.
- Where two limits are not comparable — different measures, or the same measure under different conventions — the conflict is **unresolvable and reported as such**, never guessed.
- The resolved closure is recorded on every `Run` that used it, so an old run stays explainable after adoptions change.

---

## `Project` — aggregate root

The thing being checked, and everything human about it. Deliberately holds all the state a
`Run` is forbidden to hold.

**Owns:** `RegulatoryTimeline`, project facts, parcel reference, entitlements, departures,
dispositions.

**Invariants**
- `RegulatoryTimeline` is four independent dates — application, issuance, original construction, work. Any may be absent. A predicate needing an absent date returns `UNDETERMINED_APPLICABILITY`; it never falls back to another date and never guesses.
- Every project fact carries provenance: `extracted | identified | declared`. **A fact may not be created without one.** *A suggested value accepted by a click would otherwise become indistinguishable from a measurement, and the engine would evaluate deterministically on it — the data-flow path around I1 that an import contract alone does not close.*
- Humans may `identify` — point at something the system then measures. Humans may not `measure`. A `declared` numeric quantity is permitted but every finding depending on it is marked as such wherever it appears.
- An `Entitlement` with no recorded instrument is unusable and yields `INDETERMINATE`, never a default.
- Dispositions attach to the **project**, never to a run. *The workflow is check, fix, re-check; a tool that loses judgements on every re-check punishes the loop it exists to accelerate.*
- An unmatched disposition surfaces as needing review. It is never dropped.

---

## `Run` — aggregate root

One evaluation. Immutable once complete.

**Invariants**
- Reproducible from input model hash, pack versions and resolved adoption closure alone. Nothing else may enter.
- **Carries no human judgement.** *This is what makes a run reproducible from its inputs, and what makes it structurally impossible to teach the evaluator to suppress findings that users dislike.*
- States all three status counts and all three applicability counts. Always, including when a count is zero.
- Emits a `CoverageManifest` and the report presents it **before** findings. *Otherwise coverage improves by narrowing applicability while checking less, and the number that looks like progress is the one that hides the retreat.*
- States the size of the effective rule set, not only the findings emitted.
- No path exists from `INDETERMINATE` to `PASS`. Enforced as a type-level guarantee — the aggregation functions do not accept a two-valued input — plus a property test asserting no input produces such a mapping.

---

## `Finding` — entity within `Run`

The unit of output, and the thing a reviewer argues with.

**Invariants**
- Has a `status`, an `applicability`, and a **basis**: a clause, an entitlement instrument, or a departure. Uncited is a bug, not a lesser finding (I5).
- Carries attribution: pack identity and version, the **named ratifier** of the record, and any assigned role with its derivation trace. *A finding citing a clause asserts that the clause says something; if that interpretation is wrong, the assertion is made under the product's name, and the defence is a named ratifier and a stored source quote.*
- Reports `margin` — the signed distance between measured and required — and the tolerance policy applied.
- A value within tolerance of a limit is a **near-miss**: a distinct visible outcome naming the tolerance, never silently resolved in either direction. *Designers draw to the limit, so a large share of all findings sit in that band. Reporting a failure on drawing noise destroys trust in a day; rounding up to compliance conceals a real violation precisely where violations cluster.*
- Declares its compliance route. An unmet deemed-to-satisfy rule yields a distinct outcome stating the design does not follow *that route*.
- Identity is stable across runs, derived from `(rule, basis, subject)` — never from run-scoped ordinals. *Subject identity across a revised model is genuinely hard and will be imperfect; that is an accepted open problem, and the failure mode is an unmatched disposition surfaced for review.*
- Where a model annotates a dimension disagreeing with its own geometry, that divergence is itself a finding.

---

## `CoverageManifest` — value object within `Run`

**Invariants**
- Four disjoint sets, summing to the clauses in force: with ratified rules; deliberately out of scope **with a reason each**; unrepresented; evaluated.
- "Out of scope" without a recorded reason is not a category. It is an unrepresented clause wearing a disguise.

---

## Invariant ownership map

Where to look when something is wrong, and where a fix belongs.

| Invariant family | Owner | Enforced at |
| --- | --- | --- |
| Convention present in every property name | `Observation` | construction + build guard |
| Required-vs-produced arithmetic | `ObservationManifest` | build (missing derivation) + run |
| Parameter agrees with its source quote | `ClauseRecord` | build (quote linter) |
| A draft cannot become a check | `ClauseRecord` | state transition + compiler refusal |
| Compiled artefact matches source | `RulePack` | build (compile drift) |
| Fixtures exist and run | `RulePack` | build |
| Conflict policy declared; unresolvable reported | `Adoption` | resolution |
| Four dates, no fallback | `Project` | predicate evaluation |
| Provenance on every fact | `Project` | construction |
| Dispositions survive re-runs | `Project` | re-attachment |
| Reproducibility; no human state | `Run` | construction + property test |
| INDETERMINATE never becomes PASS | `Run` | type signature + property test |
| Coverage before findings | `Run` → Presentation | report assembly test |
| Every finding cites a resolvable basis | `Finding` | construction |
| Margin and tolerance on every comparison | `Finding` | construction |
