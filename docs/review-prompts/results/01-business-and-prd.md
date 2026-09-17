# Result: business and PRD review (pass 1 of 5)

Run 2026-09-18 against `docs/review-prompts/01-business-and-prd-review.md`. Doc-only pass, by
that prompt's own constraint — no source code was read, so nothing below rests on a code check.

**Context actually read:** `prd.md` whole; `docs/decisions.md` whole (all 1,491 lines, so the
prompt's heading-prioritisation fallback was not needed); `docs/plan.md` lines 1–135, the
`### Queued` section, and 1780–end; `docs/product/user-stories/` (four files, all UI stories
reconstructed after the fact). The prompt's three "excerpt" attachments did not exist as files;
the repo originals were read instead.

**Disposition is recorded in `docs/decisions.md`, in the two entries dated 2026-09-18.**

| Finding | Disposition |
| --- | --- |
| F2, F9, F10 | Fixed the same day — wording and status defects with one correct answer. |
| F6 | **Decided:** nothing that is not an established PASS counts as a PASS. Near-miss and route-not-followed are INDETERMINATE with their own reason and their own count. In `prd.md` 5.7 and 12. |
| F3 | **Decided:** coverage is reported bounded-below; the independent clause-enumeration step waits for the first authored pack. In `prd.md` 5.7 and 12. |
| F1 | **Deferred by decision** to the start of Phase 4, recorded as an open question in `prd.md` 5.4 with the multi-pack collision spelled out, and `docs/plan.md`'s Phase 4 item gated on it. Explicitly not open to a local answer at implementation time. |
| F4 | **Deferred by decision:** gate 2 stays unrun and `prd.md` 11 stays unamended; the first real office is the measurement. The exposure is written down in the decision log rather than softened in the PRD. |
| F5 | Half-closed: the risk is now named in `prd.md` 6, per dependency, with what goes dark. Whether vendoring a fork is a permitted I3 exception is **open**. |
| F7 | **Logged unowned** — I3, I5, I6 and I7 name no verification path in `prd.md`; whether they get mechanisms or leave the word "invariant" is a framing call not yet taken. |
| F8 | **Open** — no commercial sibling document exists and none is scheduled. |

---

# Findings, most important first

## F1 — A rule pack's role selector has no execution mechanism, and two passages rule out the only one available (item 1)

> §5.3: "Habitable, egress component, light well, occupancy class and fire compartment are designations a code confers, **assigned at check time by a selector inside a rule pack — never stored, never a property name**, never read from the input file."
> §5.3: "one model can be checked under several codes at once and **receive different role assignments for the same element**."
> §5.4: "IDS is alphanumeric by design… It **cannot compute**, cannot compare one property against another, and cannot express geometric or topological conditions."
> §5.4: "The move that recovers the geometric checks is a derivation pass: compute each observation once, **write it back onto the model as an IFC property named for its convention**, and every rule becomes a plain IDS bounds check against a property that now exists."
> §5.4: "**Derived** — a role computed under a specific pack, **never stored**, always carrying its derivation trace."
> §5.5: "A rule, pack, derivation or **property name containing a country, a code, a jurisdiction or a clause reference fails the build**."
> §5.6: "ifctester, run over the derived model with the applicable packs' IDS files."

Three kinds of observation exist and the derivation pass materialises them as named IFC
properties; roles are one of the three kinds and are explicitly excluded from materialisation.
The only stated evaluator is ifctester over IDS, which §5.4 itself says cannot compute. So a
role-based rule has nowhere to run: not in IDS (cannot compute the role), not in the derivation
pass (would store it, and would need a property name scoped to the pack — which §5.5's guard
forbids spelling, since pack identity is a code/jurisdiction reference). And `docs/decisions.md`
(2026-09-02, "A selection of several packs is one run with several rule sources") has already
committed to one model object per run with `run_check` called once per pack, so two packs'
conflicting role assignments in one run would collide on one shared property regardless.

**Why it matters.** §5.3 says this mechanism "is what makes I4 real instead of aspirational." It
is also most of v0's own check list (§9: light well area and proportion, basic egress and fire
separation) — every one of those turns on a code-conferred role. If the mechanism is unspecified
when the derivation layer is written, the cheap local answer is to write the role onto the model
as a property, which silently compiles one jurisdiction's reading into the engine: exactly I4's
failure mode, arriving through the door §5.3 was written to close.

**Resolution.** Add to §5.4/§5.6 a stated execution site for a pack selector, and answer one
question in the document: *under which named property does a pack's "habitable room" selector
present its result to ifctester, and what prevents two packs in one run from writing that
property differently onto the same model?* The three candidate answers each need a PRD edit: a
pack-scoped property namespace (amend §5.5's guard to admit a pack identity that is not a
jurisdiction string, and state per-pack run isolation — a model copy or namespace per pack
version); or route role-based rules to the non-IDS host §5.5 already has "under evaluation"
(`ifc-gherkin-rules`), which makes that evaluation blocking rather than optional; or drop "never
stored" in favour of "cached against a pack version," which §12's reopen clause already
half-concedes.

## F2 — "The only place permitted an inference client" contradicts §5.9's agent, and three different versions of that contract are now on record (item 1)

> §8: "Codification is a separate service, and **the only place in the system permitted an inference client (I1)**."
> §5.9: "**Inference runs on self-hosted open-weight models by default**, for latency, cost, and keeping client drawings inside the deployment's own network." / "The **one outbound inference call** anywhere in the system is codification (8)."
> §3: "Explaining and ranking findings are permitted, because they consume results rather than produce them."
> `docs/plan.md`, Constraints: "**The assistance layer may not hold a model handle.** The data boundary is enforced the way I1 already is here, by an import contract."
> `docs/decisions.md`, "No inference client in the evaluation path": "**The engine package** may not import an LLM SDK or an HTTP client."

§8's sentence is unqualified; §5.9's is qualified to *outbound*. Read literally, §8 forbids the
v1 agent layer from existing. The decision log holds a third, much narrower formulation (the
engine *package*), which would permit an inference client in the report path or anywhere else
outside that one package.

**Why it matters.** §3 stakes I1 and I2 on being "machine-checked import contracts, not
documented principles" and on being showable to "a customer or a regulator." A contract file is
only as good as the sentence it was transcribed from, and there are three sentences. This is the
one invariant the document says is already mechanised, so the ambiguity is more expensive here
than anywhere else.

**Resolution.** Edit §8 to read "the only place permitted an **outbound, hosted** inference
call," and add to §5.9 the contract's actual subject in one line: which components may import an
inference client (codification service, assistance layer) and which may not (engine, derivation,
report generation, and anything that can hold a model handle). Then reconcile
`docs/decisions.md`'s engine-only wording to the same statement.

**Fixed 2026-09-18** — §8 qualified, §5.9 carries the component list, §12's I1 row names the
scope. The engine-only contract in force today is the narrowest of the three and violates none
of them, so no code change follows from this.

## F3 — The coverage manifest's denominator is authored by the same pipeline as its numerator (item 8)

> §5.7: "Every run emits a coverage manifest: **clauses in force under the resolved adoptions**, clauses with ratified rules, clauses deliberately out of scope with a reason, and clauses unrepresented." / "'this run evaluated 12 of 80 provisions' is a roadmap, a truthful sales conversation, and a defence." / "A report covering a fraction of a code while presenting as complete manufactures confidence, which is worse than no report at all."
> §5.5, pack layout: "`clauses/` clause index, citation text, provenance."
> §8, step 1: "An LLM API call reads the regulatory text and **emits one draft record per checkable provision**."

The "80" comes from the pack's own clause index, and the index is produced by the same
extraction-and-ratification pipeline that produces the rules. A chapter codification never
ingested is absent from both sides of the fraction. The manifest then reports 12 of 80 when the
code has 300 provisions, and the run reads as fully-scoped-and-partially-evaluated rather than as
partially-scoped.

**Why it matters.** This is the document's own named worst output, moved up one level into the
number that exists to prevent it — and I7's machinery cannot catch it, because every I7 mechanism
operates on checks that exist. Gate 5 measures what the manifest says in front of an architect;
nothing measures whether the denominator is the whole code. §5.7 also warns that "coverage
improves by narrowing applicability while checking less"; an incomplete index is the same retreat
one step earlier, and unlike the applicability case the document names no guard for it.

**Resolution.** Add to §5.7 that the coverage denominator is authored **independently** of the
rule records — a clause-enumeration step (§8 "step 0") that indexes every clause of a source and
is ratified as complete for a named chapter scope — and that a pack whose index is not
ratified-complete reports coverage as bounded-below ("at least 12 of the 80 provisions indexed;
chapters 4–7 not yet indexed") rather than as a fraction that implies a complete denominator. The
question to answer explicitly: *who states, and how is it checked, that a pack's clause index is
the whole code rather than whatever extraction happened to find?*

## F4 — Gate 2 could not have preceded the market choice, and the one decision that mentions it demotes it (items 2 and 5)

> §8: "**The first deployment target is Iran**, so the first packs are مقررات ملی ساختمان… These sources are public — a materially better position than markets where an equivalent product needs a data licensing agreement — and the published sample reviewed drawings are labeled validation data."
> §11, gate 2: "**In the first target market**, how do offices that actually submit to plan review author their work? This decides **whether v0's import path has enough reachable users to be worth shipping**, and whether v2's connector has a market… Ask twenty offices which of the three they are; no files and no engineering required."
> `docs/decisions.md` (2026-09-02): "This removes the overlay, marked sheets and BCF export from the MVP, and with them **removes gate 2 from the MVP's critical path entirely**."
> `docs/plan.md`: "None has been answered." / "Nothing in Phase 3 is blocked on them; most of Phase 4 is."

Gate 2 is scoped *to* the first target market, so by construction the market was chosen first.
The recorded justification for Iran (§8) is entirely supply-side — corpus availability, public
sources, labelled validation data — and says nothing about how those offices author. The only
place gate 2 appears in `docs/decisions.md` narrows it from "is v0 worth shipping" to "what comes
after the report," and §11 was never amended to record that reclassification.

**Why it matters.** Phase 3 is v0's import path, being finished now, and §5.2 states that "almost
every check is space-based" and that "a careless export omits IfcSpace entirely." Gate 2 is the
document's own test of whether the target market's offices produce that input at all. The
document calls this test cheap and binding, twenty phone calls; it has not been run, and the
decision log has quietly reduced the consequence of not running it rather than paying for it.

**Resolution.** Two edits, one of which is free. Either run gate 2 as written, or amend §11 to
say plainly that gate 2 has been reclassified as post-v0 and that v0 ships as an unvalidated bet
on market shape — with the reason. Separately, add a §12 row for the market choice itself ("first
deployment target is Iran, chosen on corpus availability") with an explicit reopen condition, so
the strongest commitment in the document stops resting on a subordinate clause in §8.

## F5 — Three single-maintainer dependencies carry named v0 checks with no fallback, and I3 forbids the obvious one (item 7)

> I3: "**We do not build what the open ecosystem already ships.**"
> §6: "This inventory is expected to change as upstream moves. **Adding** an inherited component is a routine edit; **replacing our code with an inherited one** is always the preferred direction of change."
> §5.4 table: `topologicpy` → "Space adjacency and connectivity", "Route travel distance, dead end", "Fire-separation adjacency"; `ifcgref` → "Georeferencing to the parcel"; `IFC_BuildingEnvExtractor` → "Building footprint / envelope".
> §5.4: "The property graph a spatial question needs already exists — **topologicpy's dual graph supplies containment and connectivity**."
> §5.9: "The agent reads the observation store and the **topology relations of 5.4**."
> `docs/decisions.md` (2026-09-02, five repos): "**Three of the five had their first and last commit on the same day.**"

§6 anticipates upstream *moving*, never upstream *stopping*. The document does record fallbacks
where it expected to need them — compiled rule packs "if IDS coverage stalls," Bonsai's pipeline
if sheet furniture becomes required, "reconsider" clauses on BIMserver and the custom schema — so
the absence here is an omission rather than a style.

Specifically, what goes dark:

- **`topologicpy`** — space connectivity, travel distance, dead-end length, fire-separation
  adjacency. That is §9's "basic egress and fire separation" in full, *and* the property graph
  that §5.4 and §5.9 both declare to be the one queryable artifact. Its loss reopens a decision
  §5.4 records as closed ("no graph database"), because the stated reason for closing it was that
  topologicpy already supplies the graph.
- **`ifcgref`** — the georeferencing join, hence the entire parcel channel, hence "site coverage
  and density against the zoning envelope, setback" (§9) — which §5.3 calls "two of the
  highest-frequency rejection categories in real plan review."
- **`IFC_BuildingEnvExtractor`** — footprint and envelope, so site coverage a second time. It is
  also a fragment salvaged from `GEOBIM_Tool`, which §6 rejects as a whole, so its maintenance
  base is narrower than the table implies.

The team already applies the abandonment test to repositories it *evaluates* (the commit-date
observation above) and has never applied it to the inventory it *depends on*.

**Resolution.** Add one column or one line per entry in §6: the capability, and the fallback if
the dependency stops. Then state the rule — a dependency whose loss would take a §9 v0 check dark
needs either a named replacement or an explicit acknowledgement that the check rests on it. The
question I3 forces and the document never asks: *if `topologicpy` is abandoned, is vendoring a
fork a permitted exception to I3, or do those checks become INDETERMINATE by design?*

## F6 — Status is closed at three values while §5.7 keeps declaring new "distinct outcomes," and the mapping is unstated (item 8)

> §5.7: "**Status is three-valued: PASS, FAIL, INDETERMINATE.**" / "**Every run states all three counts.**"
> §5.7: "Values within tolerance of a limit are near-misses: **a distinct, visible outcome** naming the tolerance applied, never silently resolved in either direction."
> §5.7: "An unmet deemed-to-satisfy rule **yields a distinct outcome**, and the report states that the design does not follow that route rather than that it is non-compliant."
> §12: "Findings and applicability are three-valued… **Never. The reason taxonomy grows; the values do not.**"

At least three outcomes are declared distinct — near-miss, deemed-to-satisfy-not-followed,
UNDETERMINED_APPLICABILITY — against a status enum the document closes permanently at three.
Every one of them must land in one of the three counts, and the document never says which. Both
natural-looking choices flatter coverage: a near-miss that clears the limit reads as PASS, and
"does not follow this route" reads as not-FAIL.

**Why it matters.** The three counts are what a buyer, an architect and a plan reviewer actually
read, and §5.7 predicts "a large share of all findings sit in that band" near the limit — so the
unstated mapping governs the largest bucket in the report. `docs/decisions.md` shows this exact
instinct already had to be refused once in code ("A requirement that evaluated nothing is
explained, never suppressed" — the tidy-up was to hide the row that said nothing was checked). A
document that leaves the mapping open is inviting the same pressure at the aggregate level, where
it is much harder to see.

**Resolution.** Add a table to §5.7: every distinct outcome × which of the three counts it
increments × whether it also surfaces as its own count. And state the default as a rule, in the
same voice as "INDETERMINATE never becomes PASS": *anything that is not an established PASS is
not counted as a PASS.*

## F7 — Of seven invariants, two are machine-checked, one is mechanised elsewhere, and four name no check at all (item 3)

> §3: "I1 and I2 are **machine-checked import contracts, not documented principles**… violation fails the build."
> §5.5: "Two build-time guards. A rule, pack, derivation or property name containing a country, a code, a jurisdiction or a clause reference fails the build — **I4 enforced mechanically rather than remembered**."
> I3: "We do not build what the open ecosystem already ships." — no check named anywhere.
> I5: "Every finding cites a resolvable basis… **An uncited finding is a bug, not a lesser finding.**" — no check named.
> I6: "No relationship with the software vendors… **This is permanent, not a stage to grow out of.**" — no check named.
> I7: "**Every way a limitation could read as a pass is closed explicitly**… Section 5.7 is this invariant made concrete, and it is the one users are actually buying." — §5.7 states behaviour; no verification path.

I4 is mechanised (§5.5), so the PRD's own pattern of "state the guard beside the invariant" is
established and simply not followed for the other four. Ranked by what the gap costs:

- **I5** is the cheapest to close and the most load-bearing for defensibility: a basis is a
  required field, so a finding without a resolvable one should fail report generation, and a pack
  whose clause index cannot resolve a cited basis should fail CI. One sentence.
- **I7** is the one the document says users are buying, and its only verification path lives
  outside the PRD, in `docs/decisions.md` ("A rule that checked nothing never passes" with its
  cardinality table, and the totality test over `ReasonCode`). The PRD does not reference it, so
  a reader of the PRD alone has no reason to believe I7 is checkable.
- **I3** and **I6** are auditable cheaply if anyone states the audit: I3 by the rule in F5 above;
  I6 by a manifest check that the connector depends on no vendor SDK, account, or online endpoint
  — which matters most precisely because the connector is the one component that ships to user
  machines.

**Resolution.** One clause per invariant naming its check, in §3 beside each. Where no check
exists and none is intended, move the item out of "Invariants" into a "Commitments" list, so
"invariant" keeps meaning "the build fails."

## F8 — The commercial gap is real, and a sibling document is missing (item 6)

§4 names the primary user ("the architect or design office preparing drawings for a building
permit") and the loop being attacked; §8 argues the market on corpus supply; §5.7 claims coverage
reporting is "a truthful **sales conversation**"; §11's gate 2 makes "worth shipping" an explicit
commercial question. Nothing anywhere states who signs, what they pay, what a resubmission cycle
costs them today, or what they would compare this to.

Checked for a sibling: a case-insensitive search across `docs/` and `prd.md` for pricing, price,
seat, subscription, billing, revenue, competitor and willingness-to-pay returns nothing but the
review prompt asking the question and one line in §5.11 saying analysis packages "are connector
targets, not competitors." The four files in `docs/product/user-stories/` are UI stories,
explicitly "reconstructed… after the fact" (2026-09-06 and 2026-09-12) from shipped screens.

So: **not** a defect in `prd.md`, whose stated job is engineering source of truth, but a real gap
in the document set. It is load-bearing for two things already in the PRD — gate 2's "worth
shipping" judgement and §5.7's sales claim both require facts nobody holds.

**Resolution.** One page outside `prd.md`: the buyer inside a design office, a pricing hypothesis
(per seat, per project, per submission), the current cost of a resubmission cycle in the target
market, and the two or three alternatives an office actually compares against (in-house
checklist, a consultant, an existing checker). Gate 2's twenty phone calls can collect the
cycle-cost datum in the same conversation at zero extra cost — which is an argument for running
gate 2 sooner, not a separate project.

## F9 — `docs/plan.md` runs two disagreeing status systems, and the stale one is on top (item 9)

Phase-level DONE markers are substantiated, so the specific thing item 9 hunts for is absent —
see the "no issue found" list below. What is present is task-level drift inside the same file:

> Phase 3 header: "**T-0033 remains unbuilt**, and two findings from T-0032's review… the download button a real user would press **has never been executed by any test (T-0053)**. T-0051's review then found the same lost-dispatch hazard **still open** upstream, where it strands the check itself (**T-0056**)."
> Lower in the same file: "**T-0033 — the measured upload ceiling, and the poison message. Done 2026-09-03.**"; "T-0053 — the download button had never executed…"; "~~**T-0056**…~~ **Done**."
> `### Queued`, still unstruck: "- **T-0029**… - **T-0030**… - **T-0031**… - **T-0032**… - **T-0033** — the measured upload ceiling…" — directly beneath two entries that read "~~**T-0027**~~ **Done 2026-09-02.** … (**Stale bullet, never struck through when it landed — corrected 2026-09-14.**)"

The file diagnosed this exact pattern on 2026-09-14, fixed two bullets, and left the next five in
the identical state. The Phase 3 header — the first thing a reader hits — asserts three items open
that the same file records as done.

**Why it matters.** The direction is safe (status behind the work, not ahead), so no correctness
claim is inflated. The cost is coordination: a coordinator, reviewer or new reader working from
the header re-queues finished work or re-opens closed findings, which the file's own 2026-09-14
note shows already happened once.

**Resolution.** Pick one status source. Either strike the landed bullets in `### Queued` in the
same pass they land, or delete the `### Queued` mirror and let "What has landed" plus an unstruck
backlog be the only two lists. Rewrite the Phase 3 header to carry a date and no task numbers, so
it stops being a second status record that has to be maintained.

**Fixed 2026-09-18** — the five stale bullets are struck with the same annotation the 2026-09-14
pass used, and the Phase 3 header is rewritten to state the phase's condition without naming
task numbers it cannot keep current.

## F10 — Minor: §12 reads as though user rule-set upload left the product; the decision log says only the UI did (item 4)

> §12: "Rules ship as a selectable catalogue (jurisdiction, region, version); **user upload is post-MVP**."
> `docs/decisions.md` (2026-09-04): "remove it from the frontend now… **The backend `RuleSet` model, its API, and the e2e fixtures that seed it are explicitly left alone in this pass** — not a statement that they're staying long-term."

Documentation drift in the safe direction, recorded honestly in the decision with a reopen
clause, and flagged only because §12 is the row someone would quote in a customer or security
conversation. One parenthetical in the §12 row ("the upload API remains, unsurfaced") closes it.

**Fixed 2026-09-18** — §12's row now says the API remains and is unsurfaced.

---

# Checklist items with no finding

- **Item 4 — non-goal drift.** Checked, no issue found beyond F10. No entry in
  `docs/decisions.md` edges toward any §10 non-goal. The log runs the other way: the rule
  catalogue's seeded rows carry `jurisdiction="sample"` because "inventing a real jurisdiction,
  region or version for a pack that does not exist is refused"; severity was defined as status
  rather than invented from IFC class, on the explicit grounds that inventing a ranking "would be
  the engine asserting an importance the rule author never stated"; and `RESOURCE_EXHAUSTED`'s
  detail sentence deliberately does not name the OOM killer as the cause because `_claim` cannot
  observe it. Three independent instances of the non-goal holding under pressure is stronger
  evidence than its absence from the log would be.
- **Item 9 — phase DONE markers.** Checked, no issue found. Each of the three has a dated,
  substantive paper trail in `docs/decisions.md`: Phase 0 (DONE 2026-09-01) ↔ "Inherit the
  IFC/IDS toolchain" ("**Verified 2026-09-01**, not assumed") and the three-valued entry's
  113-vs-12-doors measurement of the same date; Phase 1 (DONE 2026-09-01) ↔ "2026-09-01 — Reset
  the repository to the MVP path" with the commit hash and recovery branch; Phase 2 (DONE
  2026-09-02) ↔ "2026-09-02 — A base built to be continued" plus the transcript of eleven real
  endpoint calls in the plan itself. Phase 3 is marked IN PROGRESS and the file argues against
  marking it done. Dates were checked for internal implausibility against the sequence the docs
  imply; no decision is referenced by an earlier entry than the one that settled it.

---

# Verdict

The PRD is exceptionally strong as product reasoning — §2's oracle argument, §5.7's three-valued
discipline, and the unusual habit of recording rejections with reopen conditions are all doing
real work, and F4's and F7's gaps are gaps in *enforcement and sequencing*, not in thinking. It
is sound enough to keep building Phase 3 against as-is: nothing in F1, F3 or F6 touches the MVP's
upload-select-report sentence. It is **not** sound enough to plan Phase 4 against, because Phase
4's first two items are the derivation layer and rule packs, and those are precisely where F1 (no
execution site for a role selector, with the two available answers each ruled out by a different
section), F3 (a coverage denominator authored by the pipeline it is supposed to audit) and F6 (an
open set of distinct outcomes against a permanently closed three-value enum) would each be
resolved by whoever writes the code first, locally and defensibly, in the direction that compiles
one jurisdiction into the engine or flatters a count. Those three are the blocking edits. Two
more are cheap and should go in the same pass: one sentence fixing §8's inference-client scope
(F2) and one fallback line per single-source dependency in §6 (F5). The remaining two are not
document work at all — run gate 2's twenty phone calls before Phase 3 closes and collect the
resubmission-cost datum in the same call (F4, F8), because the document already spends commercial
facts it does not have.
