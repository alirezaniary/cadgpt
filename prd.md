# Product requirements: an agentic engineering system for buildings

## 1. Vision

Claude Code, for civil and architectural engineering.

An agent that works inside the engineer's own authoring tool, knows the building regulations that apply to a project, and operates the way a coding agent operates: it reads the current state, proposes a change, executes it, verifies the result, and cites its authority for every move.

The end state is design and calculation — describe a building, get it modelled, sized and detailed, with each decision traceable to a clause or a computation. The first shipped version is only the verification half, because verification is what makes the authoring half possible.

Two properties hold throughout this document.

**The agent lives where the work lives.** Claude Code did not win by asking developers to upload a zip and download a patch; it ran in the terminal they were already in. Past the first version, this product does not ask an engineer to hand over a file and receive a document. It attaches to the authoring application and works there (5.10).

**The agent is only as good as its oracle.** Section 2.

## 2. The core insight

Coding agents work because compilation and tests give free, instant, unambiguous verification. Building design has no equivalent. A wrong seismic factor, a stair 15 cm too narrow, a light well below the required proportion — none of these produce an error. The model opens fine and the drawing looks correct. The mistake surfaces at plan review, or on site, or never.

So the product's first job is to manufacture that oracle. The compliance engine is not a feature of the design agent; the design agent is what becomes possible once the compliance engine exists. The phase plan is ordered by that dependency, not by ambition.

## 3. Invariants

These hold across every version and are not renegotiated per feature.

**I1 — The language model never evaluates a rule.** It helps author rules and explains findings. Evaluation is deterministic code.

**I2 — The language model never authors geometry freehand.** It fills parameters on typed generators and calls typed API commands. Free-form geometry from a language model produces walls that don't close and cores that don't align between floors, and nothing in the system can detect it. Parameter filling is what the model does reliably.

I1 and I2 are machine-checked import contracts, not documented principles: no module in the checking engine may import an inference client, a model SDK, or the assistance layer, and violation fails the build. Both erode the same way — one hard rule that is tedious to express declaratively, one geometry case a model could just handle — and each concession is locally defensible and collectively fatal, because a checker that is deterministic ninety-five percent of the time gives no guarantee at all: the user cannot tell which five percent they are looking at. CI enforcement also turns an abstract claim into a contract file a customer or a regulator can be shown.

Explaining and ranking findings are permitted, because they consume results rather than produce them. The boundary is production of a verdict, not proximity to one.

**I3 — We do not build what the open ecosystem already ships.** The parser, geometry kernel, topology engine, rule format, rule runner, drawing generator, validation service, viewers, application connectors and structural solvers are all inherited. We write the derivation from geometry to checkable quantities, the tooling that turns regulations into rule packs, and the agent that drives it all. Section 6 is the inventory; section 7 is the residue.

**I4 — The product is jurisdiction-agnostic.** No regulation, code cycle, municipal rule or local standard is hard-coded anywhere in the engine. A jurisdiction is a set of loaded rule packs and nothing else. The engine cannot tell which country it is running in, and adding a country is authoring work, not engineering work.

**I5 — Every finding cites a resolvable basis** and every calculation cites a standard and shows its inputs. An uncited finding is a bug, not a lesser finding. A basis is usually a clause, but not always — see 5.7.

**I6 — No relationship with the software vendors.** We work with their software, never with them. Public scripting interfaces only, local installation only; no account, marketplace, partner programme, certification, or dependency on a vendor's online service. This is permanent, not a stage to grow out of.

**I7 — The system never asserts compliance it did not establish.** Every way a limitation could read as a pass is closed explicitly: unevaluable checks, unfireable rules, unencoded clauses, alternative compliance routes, and near-limit measurements each have their own reported outcome. Section 5.7 is this invariant made concrete, and it is the one users are actually buying.

## 4. Users and the problem

Primary user: the architect or design office preparing drawings for a building permit.

The loop being attacked is near-universal, whatever the jurisdiction. Drawings go to a plan-review authority; the designer submits, waits, receives a rejection list, reworks, resubmits. Each cycle costs weeks, and the findings are largely mechanical — dimensions, ratios, counts, clearances that a machine can measure exactly and a human reviewer measures slowly. The product runs the reviewer's own checks before submission, so the designer sees and fixes the same findings on their own schedule.

Later users: the same architect generating compliant options rather than only checking finished work; the structural engineer sizing and verifying; eventually the reviewing bodies themselves.

## 5. System shape

### 5.1 The pipeline

```
Model in  →  gate  →  derive  →  check  →  report and overlay
              │         │          │              │
          inherited  mostly     inherited     partly ours
                     inherited
```

Every stage but derivation and presentation is an inherited component with our configuration on top. Derivation is where geometry becomes measurable quantities, and it is the only place geometric reasoning lives.

All product logic runs on the server. In the connector phases the client is an executor and a renderer with no logic in it, so proprietary logic never ships to a customer machine.

### 5.2 Ingest

Input is a model file the user provides: IFC4, and IFC2x3 in degraded mode. No extraction from 2D drawings, no layer heuristics, no computer vision.

The risk this concentrates is export quality. Almost every check is space-based, and a careless export omits IfcSpace entirely or ships it without base quantities.

**Measure, never invent** governs the whole ingest stage. Computing a quantity from geometry the designer authored — the area of a room they drew, the width of a stair they placed — is measurement, and it is safe: the intent is theirs and we only put a number on it. Synthesizing a semantic entity the designer did not author is invention, and it is forbidden. Rebuilding absent spaces from wall and slab surfaces means deciding for ourselves where the rooms are, what they are for, and where one ends and the next begins, then checking our own guess against the code and reporting the result as their design. A false finding on invented geometry costs more trust than the missing check was worth, and a false pass on it is worse.

The gap is closed at the source instead, in three steps.

**Pre-flight, in the user's own software.** A small tool we ship, running inside the authoring application, that inspects the model before export and names exactly what is missing for the checks the user wants: rooms not placed or not bounded, spaces unnamed, levels unset, units or georeferencing wrong, export settings that will drop what we need. It reports in the user's language, lists the specific elements, and lets them select and jump to each one. It can then drive the export itself with a correct preset, so the export dialog stops being a lottery.

It is strictly read-only — it never modifies the model, never adds a space, never repairs anything. That constraint is what makes it safe to install and what separates it from the invention just ruled out. It is also the first slice of the connector (5.10), built read-only and advisory; the later connector is its continuation rather than its replacement.

**Gate, on the server.** The backstop for models that arrive without pre-flight. It states which entities or quantities are missing, in the same language and shape as the pre-flight report, before any rule runs. It never guesses and never repairs, and it is inherited rather than written (6).

**Partial results, never silent ones.** A model missing one input does not fail wholesale. Every check whose inputs exist runs; the rest are reported as an explicit list with a reason each (5.7). A check that did not run is visible as a check that did not run — never absent, never quietly passed.

Published export presets accompany the product for each major authoring application, so the common case is a one-time setting rather than a support conversation.

### 5.3 The model

The IFC model, in memory via IfcOpenShell, enriched in place by the derivation pass. There is no separate internal model and no extraction step: the input model and the checked model are the same object.

**Physical kind, never code role.** The model records what a thing is, measurably and observably, independent of any code: a stair is a stair, a vertical void is a shaft, a bounded volume is a space, a declared intended use is a program use. Habitable, egress component, light well, occupancy class and fire compartment are designations a code confers, assigned at check time by a selector inside a rule pack — never stored, never a property name, never read from the input file.

The test is clean: if two authorities could disagree about it, it is a role. Two authorities cannot disagree that a shaft is 2.1 m by 3.4 m; they routinely disagree about whether it qualifies as a light well. Most vocabulary that feels like building vocabulary is code vocabulary — "habitable room" has incompatible definitions across traditions, and whether a basement counts as a storey for density is a jurisdictional answer, not a physical one. Any of these becoming a field compiles one country's code into the engine and makes the second country a fork rather than a configuration. This is what makes I4 real instead of aspirational, and it pays off directly: one model can be checked under several codes at once and receive different role assignments for the same element.

A file that labels a stair as a fire stair records the designer's claim, not a determination. Such labels enter as program use or as annotation evidence and remain inputs to a selector, never substitutes for one — otherwise a mislabelled model passes a check it should fail. The same applies to IFC predefined types, which encode regulatory readings we do not inherit.

**Every quantity carries its measurement convention, in its name.** Codes do not set limits; they set limits under a convention, and the conventions differ. Floor area may be measured to outside face, inside face or centreline, including or excluding shafts, stairs, external walls and balconies; clear width at the narrowest point, at a stated height above the walking surface, or between handrail projections. Two codes can state what looks like the same limit and mean materially different things. A bare number carries none of this, so a bare number is not a quantity and does not appear in the model, in a rule, or in a finding. Because IDS matches a named property, the convention lives in the name:

```
Pset_ACC_Site      CoveredArea_FootprintGross, FloorAreaRatio,
                   Setback_North/South/East/West
Pset_ACC_Stair     ClearWidth_Narrowest, ClearWidth_BetweenHandrails,
                   Headroom_Minimum, RiserHeight, TreadLength_AtWalkingLine,
                   NumberOfRiser
Pset_ACC_Space     NetFloorArea_InsideFace, NetFloorArea_Centreline,
                   ClearHeight_Structural, ClearWidth_Narrowest
Pset_ACC_Shaft     PlanArea_Net, MinPlanDimension, ServedHeight, ProportionRatio
Pset_ACC_Parking   StallLength, StallWidth, ManeuveringClearance, StallCount
Pset_ACC_Route     TravelDistance, ExitWidth_Narrowest, DeadEndLength
```

Without this, an engine running a second jurisdiction is silently wrong rather than obviously wrong: not a crash, but a plausible number compared against the wrong limit — precisely the defect the product exists to eliminate, appearing inside the product. It also makes findings defensible. "84.2 m² measured inside-face against 80 m² required" is arguable with a reviewer; "84.2 m²" is not. The cost is small now and unpayable later, because retrofitting conventions means revisiting every rule, every stored quantity and every historical run to work out what was actually measured.

**Quantities that arrive in the file are claims, not measurements.** An IfcElementQuantity carries no stated convention, so an exporter's stored area is an unverified assertion about an unnamed convention. It enters as evidence and is re-derived under an explicit convention before any rule uses it — which is why computing absent quantities (5.2) is not a concession: computing under a named convention is stronger than trusting a number whose convention is unknown.

**Second input channel — the parcel.** Site coverage, density and setback are checked against the cadastral parcel boundary and the applicable zoning envelope. IFC carries neither; they enter as a separate GIS channel joined to the model by georeferencing. This is a first-class input, not an afterthought: without it, two of the highest-frequency rejection categories in real plan review cannot be checked at all. Its format varies by jurisdiction; the adapter is small and per-jurisdiction, the checks that consume it are not.

### 5.4 The derivation layer

IDS is alphanumeric by design. It expresses "this entity must carry this property, within these bounds", with enumeration, pattern, bounds and length restrictions. It cannot compute, cannot compare one property against another, and cannot express geometric or topological conditions — the standard's declared scope, not an implementation gap. Against a representative architectural check list, roughly two checks in twelve survive as native IDS. The rest are geometry.

The unit both sides share is an observation:

```
(subject, property, convention) → value
```

The model side produces observations; the rule side constrains them; the join key is the tuple itself. Three kinds, and only three. **Measured** — from geometry or from analysis, carrying provenance and confidence. **Related** — a fact about two subjects, which is where the graph lives. **Derived** — a role computed under a specific pack, never stored, always carrying its derivation trace so a finding can explain why something was treated as a light well.

Two consequences are worth more than they look. Geometry input and structural analysis input are not two pipelines but two producers of the same atom, consumed by one checker — which is why calculation (5.11) extends this architecture rather than adding a second one. And where both describe the same building they corroborate: agreement raises confidence on the most failure-prone observations, and disagreement is itself a finding, because the two sources describe different buildings.

It also makes the derivation layer specifiable. "Extract the building" is not a task anyone can be held to; "produce these forty observation types, and report which ones you could not" is. Because rules are static, the observations a pack requires are known before anything runs — a manifest. Set required against produced and coverage becomes arithmetic rather than a feature someone has to build. A rule requiring an observation that nothing produces is a build error, never a silent pass.

The move that recovers the geometric checks is a derivation pass: compute each observation once, write it back onto the model as an IFC property named for its convention, and every rule becomes a plain IDS bounds check against a property that now exists. This is the model-preparation step every mature code-compliance pipeline has. It keeps the rule layer declarative and inheritable, lets a domain expert edit rules without touching Python, and makes each derived quantity inspectable and testable in isolation.

Most of the derivation is inherited:

```
Quantity                          Source
────────                          ──────
Floor / room / space areas        ifc5d.qto + ifcopenshell.util.shape
Volumes, bounding dimensions      ifcopenshell.util.shape
Space adjacency and connectivity  topologicpy dual graph
Route travel distance, dead end   topologicpy graph shortest path
Fire-separation adjacency         topologicpy adjacency (ifcclash as cross-check)
Building footprint / envelope     IFC_BuildingEnvExtractor
Georeferencing to the parcel      ifcgref
────────
Stair clear width                 ours
Shaft plan area and proportion    ours
Parking stall + maneuvering       ours
Setback against zoning envelope   ours
Clear and floor-to-floor height   ours
```

Each derivation is an ifcpatch recipe, not a loose function. ifcpatch is IfcOpenShell's existing load-transform-emit recipe architecture, already shipping recipes of this kind: CLI, argument handling, chaining and a testing convention for free, and every derivation independently runnable — which is what the strategy needs in order to be honest about its own correctness.

**Rejected, recorded so it is not rediscovered:** IFCtoLBD to RDF/BOT, then SHACL and SPARQL for the rules. A single SPARQL query can operate on parcel geometry and model elements together and compute comparisons and intersections — it dissolves the IDS limitation without a derivation pass and handles the parcel join natively. Rejected because it is a second full stack with no non-programmer authoring tools, while IDS has more than twenty implementing products and browser-based editors. Revisit only if the derivation set outgrows a handful of functions.

### 5.5 The rule layer

Rule packs are the modular compliance unit and the only place a jurisdiction exists. One pack per code, standard, jurisdiction, or firm-internal checklist — a national code, a municipal rule set and an office's own QA checklist are the same object type and load identically.

```
metadata          code name, version, jurisdiction, effective date, language
rules/*.yaml      authored clause records — source of truth
specs/*.ids       compiled IDS, generated, never hand-edited
derivations/      ifcpatch recipes this pack depends on
clauses/          clause index, citation text, provenance
tests/*.ifc       known-good and known-bad fixtures
```

**Requirements.** Every finding cites a clause, carried in the IDS specification's own name, description and instructions fields, so citation flows into the JSON and BCF output with no extra plumbing. Packs are versioned against code cycles and effective dates; a project is checked against the code in force for its permit date. Every compiled `.ids` is validated in CI by buildingSMART's IDS-Audit-tool, and every pack's fixtures run in CI — a pack whose fixtures do not run is not shipped. No language model executes inside a pack at check time. Packs are readable and editable by a domain expert who is not a programmer; that is the difference between this and a rule-checking tool that needs a consultant to configure.

**Every parameter stores the source quote it was taken from,** beside it, in the record. A mistranscribed bound produces a cited, deterministic, reproducible, wrong PASS, and the only other check on it is fixtures written by whoever wrote the rule, carrying the same misreading. With the quote stored, the error is visible in a diff, and a linter compares the encoded value against the quote — which requires numeral and unit normalisation for each script a corpus is written in.

**Time is four dates, not one.** A RegulatoryTimeline carries application date, issuance date, original construction date and work date, and each applicability predicate names which one it keys on. Applicability variously turns on when the application was made, when the permit issued, when the building was originally built, and when the work is performed; retroactive provisions ignore permits entirely and alteration provisions key on original construction. Keying on a single date silently restricts the product to new construction, and the restriction spreads, because every later rule inherits the assumption. A predicate needing a date that was not supplied returns UNDETERMINED_APPLICABILITY rather than guessing.

**Conflict is resolved by declared policy, not fixed precedence.** An adoption declares its `conflict_policy` — most-restrictive, or explicit precedence. Under most-restrictive both branches are evaluated and the finding records which governed and why. Fixed precedence is silently wrong whenever the stricter provision sits lower in it, producing a plausible limit from the wrong source. Where two limits are not comparable — different measures, or the same measure under different conventions — the conflict is unresolvable and reported as such rather than guessed.

**Normative references are pinned by edition.** A clause may bind another standard at a named edition, and an adoption may amend that binding, so an adoption is a dependency closure rather than a single node. The resolved closure is recorded on the run, so an old run stays explainable after adoptions change. The data model is fixed now and the transitive resolver is built when the first rule needs one — dimensional and planning requirements largely do not reference external standards; material and assembly requirements do. Capturing it later is not possible: the information is lost at ingestion, not merely unmodelled.

**Parcel entitlements and project departures are parameter sources.** Some binding constraints attach to a parcel rather than to a text, and some are granted to a single project by an authority empowered to depart from the general rule — a variance, dispensation, exemption, or approved alternative. Both resolve at evaluation time exactly like an overlay parameter, keyed by parcel or by project instead of by jurisdiction, so the engine is unchanged and only the resolver knows where the value came from. Resolution order is base adoption, then jurisdiction overlays outermost to innermost, then parcel entitlement, then project departure. Modelling a per-parcel value as a jurisdiction produces thousands of one-parcel jurisdictions and no way to say which instrument granted what; modelling it as a project fact the designer types in is worse, because the system would then compare the architect's claimed allowance against the architect's own drawing and verify nothing. An entitlement with no instrument recorded is unusable, and its absence yields INDETERMINATE rather than a default.

**Two build-time guards.** A rule, pack, derivation or property name containing a country, a code, a jurisdiction or a clause reference fails the build — I4 enforced mechanically rather than remembered. And a derivation is promoted into the shared set only when at least three rules across at least two clauses need it; until then it lives with its rule and is counted. Rules per derivation is tracked continuously, because the failure mode of this whole approach is a derivation set that grows one-per-rule, and that failure is visible in one number.

The YAML-to-IDS compiler starts from ids-light-editor's schema rather than a new invention — it already converts human-readable YAML/JSON to IDS 1.0 XML across all facets. Compiled output is committed and regenerated in CI, with any drift failing the build: what runs must be reviewable, and a generated artefact nobody can read is not.

**Under evaluation, not decided:** buildingSMART's ifc-gherkin-rules as the host for derived-geometry rules. Gherkin feature files with Python step definitions can compute, which is precisely what IDS cannot, and the format is maintained upstream as part of the official validation service. If it holds up, some rules that currently require a derivation could stay declarative. This does not violate the no-forking-IDS constraint: it is a separate upstream format, not a private IDS dialect.

### 5.6 Checking engine

ifctester, run over the derived model with the applicable packs' IDS files. Deterministic, and reproducible from the input model and the pack versions alone. Rules that survive as native IDS and rules that needed derivation run identically — by the time ifctester sees the model, the difference has been erased.

ifctester's native output is two-valued, which 5.7 forbids. The three-valued result is produced around it, not inside it: the required-observation manifest of 5.4 is checked against what derivation actually produced, and a rule whose observations are absent is emitted as INDETERMINATE with its reason rather than handed to ifctester at all. This is a wrapper, not a fork, and it is the one place our code sits between the inherited runner and the user.

### 5.7 What a finding is

A finding is the product's unit of output and the thing a reviewer argues with. Its shape is fixed here because every layer downstream depends on it, and because I7 is not a slogan — it is this section.

**Status is three-valued: PASS, FAIL, INDETERMINATE.** INDETERMINATE is returned whenever a check could not be evaluated, and carries a machine-readable reason: missing observation, missing project fact, ambiguous subject selection, unsupported measurement convention, confidence below the rule's threshold. It is never mapped to PASS anywhere — not in aggregation, a summary count, the report, the overlay, or an API response. Every run states all three counts.

With a two-valued result, "no violation was found" and "no check was performed" become indistinguishable, and the user reads a clean report over an unchecked building — the most dangerous output this product can produce, because it is invisible and it conceals what the tool itself missed. Three values are also what make partial coverage shippable: a system that reliably reports what it could not determine is usable at seventy percent coverage, because the user knows which seventy percent, while a system that silently passes is not usable at ninety-five. It converts the largest technical risk from a correctness problem into a coverage problem, and coverage is measurable, reportable and improvable.

**Applicability is three-valued too:** APPLIES, DOES_NOT_APPLY, UNDETERMINED_APPLICABILITY. A rule whose applicability predicate needs a missing fact would otherwise evaluate false, not fire, and emit nothing at all — vanishing rather than reporting. Rules must therefore declare the facts their applicability depends on, so an unmet dependency can be named specifically.

**Every run emits a coverage manifest:** clauses in force under the resolved adoptions, clauses with ratified rules, clauses deliberately out of scope with a reason, and clauses unrepresented. The report presents coverage before findings, and the summary states the size of the effective rule set rather than only the findings emitted — otherwise coverage improves by narrowing applicability while checking less, and the number that looks like progress is the one that hides the retreat. A pack encoding a fraction of a code reports no failures for everything it never encoded and reads as clean; "this run evaluated 12 of 80 provisions" is a roadmap, a truthful sales conversation, and a defence. A report covering a fraction of a code while presenting as complete manufactures confidence, which is worse than no report at all.

**Every rule declares a compliance route:** prescriptive, deemed-to-satisfy, or functional. Most traditions permit satisfying an objective by demonstration instead of by following a prescribed recipe, and a design taking that route is lawful. An unmet deemed-to-satisfy rule yields a distinct outcome, and the report states that the design does not follow that route rather than that it is non-compliant. Reporting a competently engineered alternative as a failure trains exactly the sophisticated users whose adoption matters to distrust the tool, and in a small professional market that is not recoverable.

**Every comparison declares a tolerance policy, and every finding reports its margin** — the signed distance between measured and required. Values within tolerance of a limit are near-misses: a distinct, visible outcome naming the tolerance applied, never silently resolved in either direction. This is where a compliance tool earns or loses credibility, and it is decided by a design choice rather than by accuracy: designers draw to the limit, so a large share of all findings sit in that band. Reporting a failure on drawing noise destroys trust in a day; rounding up to compliance conceals a real violation precisely where violations cluster. Margin is also more useful than either verdict — "1199.6 against 1200 required, 0.4 mm short, within the declared 1 mm tolerance" tells the designer both that they are fine and that they have no room, which is what an experienced reviewer would say. Tolerance is declared per rule, overridable by an overlay because tolerance practice is jurisdictional, and never a global epsilon. Tolerance and rounding are separate concerns: tolerance covers measurement imprecision, while code-mandated rounding is a property of the rule and is applied exactly as the code states. Thresholds that route or classify get zero tolerance, because crossing them is binary.

**Every finding cites a basis:** a clause, a parcel entitlement instrument, or a project departure. "Every finding cites a clause" is false for exactly the checks that run first — site coverage, density and setback are frequently governed by a value attached to the parcel or a variance granted to the project rather than by a clause of general application. The requirement that a basis be resolvable and citable is unchanged; what is citable is widened.

**Every finding carries attribution:** the pack identity and version, the named ratifier of the record it came from, and any assigned role with its derivation trace. A finding citing a clause asserts that the clause says something; if that interpretation is wrong, the assertion is made under the product's name, and the defence is a named ratifier and a stored source quote rather than confidence in the pipeline.

**Every project fact carries a provenance tag:** extracted, identified — a human pointed at something the system then measured — or declared, a human stated it. Findings depending on a declared fact are marked as such wherever they appear. Humans may identify; humans may not measure. Without this, a suggested value accepted by a click becomes indistinguishable from a measurement and the engine evaluates deterministically on it — the data-flow path around I1 that an import contract alone does not close.

Where a model annotates a dimension that disagrees with its own geometry, that divergence is itself a finding. Reviewers read dimension strings while this system measures geometry, and the disagreement is a real defect reviewers look for.

**Findings carry no human judgement.** Whether one is accepted, waived under an alternative-compliance provision, disputed, or already fixed is a disposition — authored once by a person against the project rather than against a run, surviving re-runs and re-attaching in the next one. The workflow is check, fix, re-check; if judgements are lost on every re-check, the second run is worse than the first and the tool punishes the loop it exists to accelerate. Keeping evaluation free of human state is also what keeps a run reproducible from its inputs and pack versions, and what makes it structurally impossible to teach the evaluator to suppress findings that users dislike. This requires findings to have stable identity across runs, derived from rule, basis and subject rather than from run-scoped ordinals — which in turn requires subject identity to survive re-import of a revised model. That is genuinely hard and will be imperfect. An unmatched disposition surfaces as needing review; it is never dropped.

### 5.8 Report and overlay

Two outputs from one findings set.

The report is localized, in the language and reading direction of the loaded rule packs, with findings grouped by severity, each stating measured against required with clause citation. Templated from ifctester's JSON. Right-to-left rendering and complex-script shaping are handled by arabic-reshaper, python-bidi and HarfBuzz, with WeasyPrint for PDF — a solved typography problem, not custom work.

The overlay is the product. A findings list is a document an architect skims; errors shown on the thing they just finished is something they act on. It ships in three forms:

```
Web overlay       ThatOpen Engine (web-ifc) or xeokit-bim-viewer — both open
                  source, both load and save BCF viewpoints, both support
                  2D-in-3D markers and 2D plan generation. Primary form in the
                  first version: it reaches anyone, with no install.
Marked sheets     Plan projection per storey with findings drawn on it, as SVG
                  and PDF, for an office that works on paper.
In-model markers  Once the connector exists, the finding is placed on the
                  element in the user's own tool, where they will fix it.
```

Drawing generation is `ifcopenshell.draw` / the IfcConvert SVG serializer — IfcOpenShell's own C++ svgfill module over CGAL, with auto_floorplan, auto_section, auto_elevation, storey filtering, scale, hidden-line removal, space names and areas. No Blender required. Bonsai's drawing pipeline is an option only if sheet furniture (titleblocks, composition, dimensioning) turns out to be required, and it is not required to ship.

BCF is the interchange format behind all three, via ifctester's Bcf reporter. That reporter has had open defects; its output gets a fixture test of our own and is not trusted on reputation.

### 5.9 Agent layer

Orchestration and conversation. Its tools: query the model, retrieve a clause, run a check, place a marker, execute a host command, run a calculation, call a generator. It sees extracted summaries and query results, never raw model files — a context-budget requirement first and a data-handling one second.

Inference runs on self-hosted open-weight models by default, for latency, cost, and keeping client drawings inside the deployment's own network.

### 5.10 The connector

The connector is how the product stops being a website and becomes the role model. Its first slice — the read-only pre-flight tool of 5.2 — ships with v0; the rest is deferred, and specified here because it constrains earlier decisions.

```
User's machine                          Server
─────────────                           ──────
Host application                        Agent, orchestration
Connector plugin  ◄── MCP ──►           Derivation, rules, checking
  read model                            Clause corpus and citation join
  execute command                       Report and overlay rendering
  place marker                          Solvers
```

Under I6, the connector uses only the public scripting and add-in interfaces that any user's own script may use, installs as a plain local add-in or extension folder, and depends on no vendor account, marketplace listing, partner programme, certification or online service — a constraint that is also a practical necessity in markets where those services are unreachable.

It is offline and local: it talks to the host application over localhost and to the server over one outbound channel we control. It is not a platform the user logs into, and in an on-premise deployment — which self-hosted inference already makes possible — it does not need to leave the office network. Protocol is MCP: an open specification owned by no vendor, the protocol the role model uses, and one that makes our tool definitions ordinary MCP tool definitions rather than a bespoke RPC layer.

Host targets, in priority order:

```
Revit       pyRevit is the primary surface: open source, installs per-user,
            wraps IronPython and CPython over the public Revit .NET API, and is
            already present in a large share of offices. The open-source
            community revit-mcp-server is the MCP layer over the same API.
Archicad    The Python Automation API is a plain HTTP/JSON endpoint on
            localhost with an official PyPI client — local, no account, no
            online service. Tapir is the open-source add-on that widens the
            command set, built explicitly for scripted and agent use.
Blender     Bonsai for native IFC authoring; blender-mcp for agent control.
            Fully open, no licence, no vendor at all. The reference
            implementation and the fallback host for an office that owns
            nothing commercial.
Rhino       Rhino MCP, for concept-stage work.
```

Not a target: any vendor's own first-party AI or MCP service, which routes through that vendor's account and service layer and would hand them a switch over the product. We drive each application through the same public API its users' own scripts already use.

Read is built first and completely. Write is an addition to the same component, not a new one.

### 5.11 Generation and calculation

Generators are typed parametric functions — grid, core, slab, stair, residential typologies. The agent selects and parameterizes them; it does not write geometry code (I2). Generated geometry is written into the live model through the connector rather than handed over as a file to import, and is checked by the same engine that checks human work. The authoring loop and the checking loop share one representation, which is the whole payoff of the architecture.

Calculation enters in three tiers, most trustworthy first:

```
1. Verify   Check an existing analysis against the loaded standards: seismic
            parameters, load combinations, member checks. This is a checker,
            which is what the system is already good at, and it needs no solver.
2. Size     Preliminary member sizing. sectionproperties and concreteproperties
            for section capacity; PyNite or anaStruct for the frame.
3. Analyze  OpenSeesPy where nonlinear or seismic analysis is genuinely needed.
```

Established commercial analysis packages are connector targets, not competitors. They expose scripting APIs, engineer trust lives in them, and the right move is to drive the analysis the engineer already trusts and verify its output against the standard rather than ask anyone to switch solvers. The same vendor-independence constraint applies: public API, local, no relationship.

## 6. What we inherit

Everything below is open source and either runs server-side or is an existing local plugin surface on the user's machine. This inventory is expected to change as upstream moves. Adding an inherited component is a routine edit; replacing our code with an inherited one is always the preferred direction of change.

```
Concern                        Inherited from
───────                        ──────────────
IFC parse and query            ifcopenshell
Geometry kernel                ifcopenshell.geom / Open CASCADE
Quantity computation           ifc5d.qto, ifcopenshell.util.shape
Model transformation           ifcpatch (host for our derivations)
Property writing               ifcopenshell.api.pset
Topology, adjacency, paths     topologicpy
Clash and clearance            ifcclash
Rule format                    buildingSMART IDS 1.0
Rule runner                    ifctester
IDS validation in CI           buildingSMART IDS-Audit-tool
YAML to IDS compiler base      ids-light-editor
Ingest gate / model validation buildingSMART validate + ifc-gherkin-rules
Findings output                ifctester reporters (Json, Bcf, Html, Ods)
2D drawing generation          ifcopenshell.draw / IfcConvert SVG serializer
Web viewer and overlay         ThatOpen Engine (web-ifc) or xeokit-bim-viewer
Building envelope / footprint  IFC_BuildingEnvExtractor
Georeferencing to parcel       ifcgref
GIS parcel handling            GDAL/OGR, Shapely, GeoPandas
Revit connector                pyRevit; revit-mcp-server (public .NET API only)
Archicad connector             Archicad Python Automation API (localhost); Tapir
Blender connector / authoring  Bonsai; blender-mcp
Rhino connector                Rhino MCP
DXF read (low priority)        ezdxf
Complex-script shaping, RTL    arabic-reshaper, python-bidi, HarfBuzz, WeasyPrint
Structural sections            sectionproperties, concreteproperties
Frame analysis                 PyNite, anaStruct
Nonlinear / seismic analysis   OpenSeesPy
Rule-extraction benchmark      CODE-ACCORD corpus and annotation schema
Reference architecture         CHEK (digital building permit toolchain)
Fixture testing                pytest + ifctester
```

Considered and rejected on merit:

- **BIMserver.** Maintained, but Java 8 on a Jetty 9 base that reached end of life in January 2025 with no security updates. It offers revision control and multi-user access the first versions do not need, and its checking plugins are weaker than ifctester against IDS. *Reconsider if multi-user model hosting becomes a requirement.*
- **GEOBIM_Tool as a whole.** Its planning checks are hardcoded to one jurisdiction's rules; adopting it means replacing the rule set, not configuring it (I4). Its modular successors, IFC_BuildingEnvExtractor and ifcgref, are inherited instead.
- **Bonsai's drawing pipeline as the default.** `ifcopenshell.draw` does the same job without a headless Blender dependency. Retained as an option for sheet composition only.
- **Any dependency on a vendor cloud, marketplace, partner programme, certification, first-party AI or platform service** (I6, 10).
- **A custom internal schema with a maintained IFC mapping.** Large custom surface, and it contradicts I3. Roles are never read from the file and stored quantities are re-derived under a named convention, which delivers what the mapping was for. *Reconsider only if deriving live from IFC becomes a genuine performance bottleneck.*
- **Six bounded contexts as the source-code layout.** Sized for a custom engine this document does not build. The import-contract idea (I1, I2) survives and applies to whatever modules exist. *Reconsider only if the custom surface of section 7 grows enough to need one.*
- **Compiled rule packs with handler templates and committed generated Python.** A real answer to a real problem, but it replaces the inherited runner. IDS plus ifctester stays primary; this is the recorded fallback if IDS coverage stalls (5.4, 5.5).
- **Immutable content-addressed snapshots, canonical hashing, subject lineage.** Heavy for the current stage. Reproducibility is retained in the cheap form: every run records its input model and pack versions (5.7). Subject identity returns as an open problem when dispositions arrive (12).
- **A closed vocabulary as an authored artefact, with a lexicon of namespaced aliases.** The valuable half is already policy: a rule requiring an observation nothing produces is a build error (5.4). The rest waits for a second language corpus.
- **CAD-extraction machinery** — anticorruption layer, extraction-confidence thresholds, layer-convention handling. There is no 2D extraction path (10).

Component selection is on technical merit alone. Open source licence terms are not a selection criterion and are not tracked in this document; copyleft reach does not constrain what runs on our servers. Two conditions would reopen this: raising or selling in a market where acquirer diligence makes the copyleft boundary live, and connector distribution, since that component does ship to user machines. Connector distribution is a direct download the user installs themselves, never a vendor marketplace, so no third party sits in that path.

## 7. What we write

The entire custom surface. It is deliberately small, and every item is either the product's actual asset or something nobody has written.

1. **Five or six derivation recipes:** stair clear width, shaft proportion, parking stall and maneuvering clearance, setback against zoning envelope, clear and floor-to-floor height. Everything else in 5.4 is a library call.
2. **The rule pack format** — the YAML clause record schema and its compiler to IDS, starting from ids-light-editor.
3. **The rule authoring pipeline:** the harness that drives an LLM API over regulatory text and puts drafts in front of a named ratifier, plus the quote linter that checks each encoded parameter against its source quote (8).
4. **The pre-flight tool, per host:** read-only model inspection and correct-preset export, inside the user's authoring application (5.2).
5. **The parcel channel:** cadastral and zoning ingest, and its join to the model.
6. **Basis resolution:** which packs apply under the timeline, at which code version, with parcel entitlements and project departures layered in, and the citation lookup behind each finding.
7. **The findings layer of 5.7** — three-valued status and applicability, the coverage manifest, routes, tolerance and margin, attribution and provenance — as a wrapper around ifctester. Small in code, and most of what the product actually is.
8. **Report templating and findings-marker compositing.**
9. **The agent,** its tool definitions, and the per-host connector glue not already provided by pyRevit, Tapir, or an existing MCP server.
10. **Later:** dispositions and their re-attachment across runs, the typed generators, and the standards-verification tier over the structural solvers.

## 8. Turning regulations into rule packs

The engine is empty until a corpus is loaded. Producing a corpus is a content activity driven by a language model through an API, with a human expert in review. It is not engineering work in this codebase, and it is not hand-authored by whoever is building the system. We build the format, the compiler, the review harness and the fixture runner; the pipeline produces the packs.

Codification is a separate service, and the only place in the system permitted an inference client (I1). It is artifact-mediated and never in the request path: it emits files into version control, and the engine consumes committed records. Artifact mediation is the load-bearing property, not an implementation detail — because the output is committed files rather than a service call, the engine has no runtime dependency on a model, runs stay reproducible from records alone, and the service can be offline, rewritten or replaced without touching a single guarantee. A bad codification run is then a bad diff, reviewable and revertable, rather than a bad answer already delivered to a customer.

Three constraints preserve I1 inside the one place a model is allowed:

- The model proposes records; it never emits executable code. The path from record to running check is the deterministic compiler.
- The model never authors fixtures. A rule and its proof of correctness may not come from the same generator.
- The model never proposes a term mapping by similarity or inference. Aliases are recorded from observed sources only; an unrecognised term is a gap for a human, not a guess.

Making this a service rather than a one-time exercise matches the actual lifecycle. Codes are amended, editions supersede, jurisdictions are added. Codification runs whenever the corpus changes — rarely, but forever.

The pipeline, per clause:

**Step 1 — extract.** An LLM API call reads the regulatory text and emits one draft record per checkable provision. Source text is preserved verbatim in its original language; nothing is paraphrased away. The draft is a proposal, never a merge.

```yaml
id: stair-clear-width-residential
source: <code and chapter, verbatim>
clause: <clause number as printed>
text_src: "<verbatim source-language text>"
applies_to: { entity: IFCSTAIRFLIGHT, occupancy: residential }
quantity: Pset_ACC_Stair.ClearWidth
operator: ">="
value: 1.10
unit: m
severity: blocking
exceptions: [...]
```

**Step 2 — ratify.** A named domain expert accepts, edits or rejects each draft. A proposal is not a record until a named person ratifies it, and that person is the attributable author of the interpretation. This is what makes a finding's claim about what a clause says defensible: without a ratifier, a finding citing a clause is an unsourced legal assertion carrying the product's name. The step is never skipped and never automated away, and the bottleneck it introduces is the point of it.

**Step 3 — classify.** Each accepted record is alphanumeric (the quantity is a property an exporter already writes), library-derived (the inherited column of 5.4), or custom-derived. This decides whether the record costs anything to implement, and it is the single most useful thing to know about a rule early.

**Step 4 — derive,** only for the custom ones. One ifcpatch recipe serves every rule referencing that quantity, so the corpus grows faster than the code does.

**Step 5 — compile.** YAML to IDS, mechanically. Clause id, source text and citation carry into the IDS name, description and instructions fields, which is how citation reaches the report for free. Compiled output is validated by IDS-Audit-tool in CI.

**Step 6 — fixture.** One model that passes and one that fails, minimal, committed with the rule. A rule without both is not merged.

**Measuring step 1.** CODE-ACCORD publishes 862 annotated sentences of building regulation with 4,297 entities and 4,329 relations, as a benchmark for exactly this extraction task. Use it to measure extraction quality rather than trusting reviewer attention, and build a held-out set the same way for each new source language.

**The economics.** Steps 1, 2, 5 and 6 are cheap and scale with how much code we want to cover. Step 4 is expensive and scales with distinct geometric concepts, of which there are few. The corpus is meant to become large while the code stays small.

**The first corpus.** The first deployment target is Iran, so the first packs are مقررات ملی ساختمان (the national building regulations), the municipal planning rules, and the plan-control checklists published by the engineering order for architecture, structure and electrical. These sources are public — a materially better position than markets where an equivalent product needs a data licensing agreement with the code publisher — and the published sample reviewed drawings are labeled validation data. Persian source text is preserved verbatim and the reports render right-to-left. None of this reaches the engine: it is pack content, and a second jurisdiction is a second set of packs, not a second product.

## 9. Phases

Each phase ships and stands alone. Each is a precondition for the next.

**v0 — import and review.** The MVP. The user provides a model file; the system gates it, derives, checks it against the loaded packs, and returns a localized report plus a web overlay and marked sheets, with any check that could not run named explicitly. No account, no authoring.

v0 also ships the pre-flight tool for the one or two hosts that gate 2 identifies. This is a real addition to the smallest possible scope and it is deliberate: without it, the MVP's failure mode is refusing a file and leaving the user with no way to fix it, which is not a product. Using pre-flight is optional; building it is not. It installs locally, is read-only, and needs no account.

```
Check scope: site coverage and density against the zoning envelope, setback,
parking count and dimensions and maneuvering clearance, stair clear width and
tread and riser and headroom, light well area and proportion, minimum room
dimensions, floor heights, basic egress and fire separation.
```

**v1 — conversational review.** Chat over the results: why this clause applies, what would satisfy it, what changed between code versions, what the cheapest fix is. Same engine, same findings, an agent in front of them.

**v2 — the connector, read direction.** The same checks run from inside the authoring application, findings placed as markers on the elements in the user's own model. No file handover, no export step, no quality lottery — the connector drives extraction itself. This is where the product becomes the role model.

**v3 — the connector, write direction.** Typed generators for residential typologies, conversational parameter filling, geometry written into the live model, checked by the v0 engine as the verifier. A genuine product transition rather than a feature release: checking verifies someone else's work; authoring means we produced the thing being judged, and the liability posture changes with it.

**v4 — calculation.** The three tiers of 5.11, in order. The verification tier is a checker and may pull forward into v1 or v2 if the structural corpus is ready before the generators are.

**v5 — reach.** Larger typologies, IFC4.3, infrastructure as import-and-check targets.

## 10. Non-goals

- **Generative design of bridges and other infrastructure.** The governing decisions there — site, geotechnics, span arrangement, construction sequencing — are not code-checkable, so the oracle this product builds does not extend to them. Import and check, do not generate.
- **Replacing the reviewer or the engineer's stamp.** Output is decision support with a human in the loop.
- **Replacing established structural analysis packages.** Drive them; verify their output against the standard (5.11).
- **Semantic extraction from 2D DWG, scanned PDF or raster drawings.** A 2D drawing has no semantic model to read, and building one from layer heuristics is a services-business trap. A 2D-only market is answered by gate 2, not a parser.
- **Inventing model semantics the designer did not author** (5.2). We never synthesize spaces, boundaries or classifications to make a check runnable. Missing input is reported at source by pre-flight and on arrival by the gate; it is never filled in on the designer's behalf.
- **Hard-coding any jurisdiction into the engine** (I4). A regulation that cannot be expressed as pack content is a gap in the rule format, to be fixed in the format.
- **Any commercial or technical relationship with the software vendors** (I6): partnership, certification, marketplace listing, reseller arrangement, or dependency on a vendor's online service or account.
- **Extending or forking the IDS standard.** Where IDS cannot express a rule, the answer is a derivation or an upstream format such as ifc-gherkin-rules — never a private dialect. The moment our IDS files stop being valid IDS, the inherited tooling stops being inheritable. This constraint is technical, not legal, and is independent of the licensing position in section 6.

## 11. What must be validated before building

Five questions, in this order. The first two are cheap and decide the rest.

**Gate 1 — ratification throughput.** How many clause records per day can one named domain expert accept or correct in the section 8 pipeline, and what fraction of LLM drafts survive ratification unedited? The corpus is the asset, and because a proposal is not a record until a person ratifies it, ratification throughput — not model throughput — is the real schedule driver and the binding constraint on coverage. Measure it on one chapter before committing to any coverage target. This has never been measured and it is the cheapest thing on this list.

Measure the quote linter at the same time: what fraction of drafts encode a bound that disagrees with the source quote beside it? That number is the size of the confident-wrong-PASS risk, and it is only observable during ratification.

**Gate 2 — market shape.** In the first target market, what fraction of offices that actually submit to plan review author in a semantic BIM tool at all, rather than in 2D? This decides whether v0's import path has enough reachable users to be worth shipping, and whether v2's connector has a market. Ask twenty offices; no files and no engineering required.

- If a workable fraction is on BIM: build as specified.
- If the market is overwhelmingly 2D: do not build a drawing parser. The two honest options are to lead with authoring in a host we control, so the model exists because we made it, or to sell to the reviewing bodies rather than the designers. Recommendation if this happens: the former, because the corpus and engine are unchanged either way and authoring is where the product was always going. Decide it then, in this document.

**Gate 3 — derivability, and the cost of pre-flight.** Run the ingest gate and derivation layer over five real models from five different offices, on projects of the type that actually goes to plan review. For each: are spaces present and bounded; are storey elevations recoverable; can the layer produce floor areas, room areas, stair clear width and parking stall dimensions. Then the question that decides how the product feels in practice — how many of the five pass only after pre-flight, and how much work does pre-flight ask of the designer? A pre-flight report that takes ten minutes to clear is a feature. One that takes two days is a different product, sold to a different buyer, and it needs to be known before building rather than after.

**Gate 4 — the parcel channel.** Confirm that cadastral boundary and zoning envelope data can actually be obtained for a real parcel in the first target market, in a form that can be joined to a model. Two v0 checks depend entirely on it and the answer is currently assumed rather than known.

**Gate 5 — first-run coverage.** On the same five models, what does the coverage manifest actually say — how many provisions evaluated, how many INDETERMINATE, how many UNDETERMINED_APPLICABILITY? A first run against an unfamiliar model may be dominated by the last two, which is honest and reads as failure. Whether that presentation lands as a coverage statement or as a broken tool is the single largest product-design question in v0, and it cannot be answered without real numbers in front of a real architect.

Everything downstream of these five is ordinary engineering. These are the experiments that decide the product.

## 12. Decision log

Settled; do not re-open per feature. The named section carries the reasoning — this index carries the decision and the condition that would reopen it.

| Decision | Where | Reopens |
| --- | --- | --- |
| Input is a model file the user provides; no extraction from 2D drawings | 5.2, 10 | Never for the engine — a 2D market is answered by gate 2, not a parser |
| Measure, never invent; space reconstruction from wall and slab surfaces was considered and rejected | 5.2, 10 | Never. The gap is closed by pre-flight at source, not by inference |
| Missing input produces partial results with the unrun checks named — never wholesale refusal, never silent skip | 5.2, 5.7 | — |
| A read-only pre-flight tool ships in v0 and is the first slice of the connector | 5.2, 5.10, 9 | — |
| Ingest gate is inherited from buildingSMART validate, not written | 5.2, 6 | — |
| Jurisdiction lives only in rule packs; the engine is region-agnostic | I4 | Never. A regulation that will not fit is a rule-format gap |
| The model records physical kind only; code roles are assigned at check time by pack selectors | 5.3 | A role universal across all target traditions and expensive to recompute — and even then cache it against a pack version, do not store it |
| Every quantity names its measurement convention in the property name; file quantities are unverified claims, re-derived | 5.3 | Never. If takeoff cost becomes prohibitive, cache by (element, convention, model hash) — do not drop the convention |
| Parcel data is a first-class second input channel | 5.3, gate 4 | — |
| The unit of comparison is the observation `(subject, property, convention) → value` | 5.4 | — |
| Derivation is ~6 custom ifcpatch recipes; everything else is a library call | 5.4 | If the custom set grows past a handful, reconsider the SHACL/SPARQL alternative in 5.4 |
| Rule format is IDS, compiled from YAML, never hand-edited, never forked | 5.5, 10 | ifc-gherkin-rules is under evaluation for computed rules only |
| Time is four dates; conflict resolves by declared policy; normative references pinned by edition, resolver built when a rule needs it | 5.5 | — |
| Parcel entitlements and project departures are parameter sources; a basis may be a clause, an instrument, or a departure | 5.5, 5.7, I5 | — |
| Build-time guards: jurisdictional names fail the build; a derivation is promoted only at three rules across two clauses; rules-per-derivation tracked | 5.5 | — |
| Findings and applicability are three-valued; INDETERMINATE is never mapped to PASS; coverage reported per run before findings, with the effective rule-set size | 5.7, I7 | Never. The reason taxonomy grows; the values do not |
| Every rule declares a compliance route; an unmet deemed-to-satisfy rule is reported as not following that route | 5.7 | — |
| Every comparison declares a tolerance policy and every finding reports margin; rounding is separate; routing thresholds get zero tolerance | 5.7 | — |
| Project facts carry provenance: extracted, identified, or declared. Humans may identify; humans may not measure | 5.7 | — |
| Findings carry no human judgement; dispositions are authored against the project and re-attach by stable finding identity | 5.7 | Open problem: subject identity across a revised model. Unmatched dispositions surface for review, never dropped |
| Drawing generation is `ifcopenshell.draw`; no headless Blender dependency | 5.8 | Only if sheet furniture becomes a shipping requirement |
| The connector is offline and local, deferred past v0, MCP over localhost, not a platform the user logs into | 5.10 | — |
| No relationship with any software vendor; public APIs only | I6, 6, 10 | Never |
| I1 and I2 are machine-checked import contracts; violation fails the build | 3 | — |
| Codification is a separate, artifact-mediated service — the only permitted inference client, never in the request path, ratified by a named person | 8 | Never in shape. If ratification binds, the answer is better proposals and better review tooling, not removing the ratifier |
| Component selection on technical merit alone; licence terms not a criterion | 6 | Outside-market fundraising or sale, and connector distribution |
