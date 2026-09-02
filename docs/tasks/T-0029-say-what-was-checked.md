# T-0029 — Say what was checked: the model, not the submitted drawing set

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** I7 — never assert compliance we did not establish. **Reviewer-gated.**
This task is one paragraph of copy and the difference between decision support and an implied
compliance claim.

## Why

`prd.md` §5.7 closes with a requirement this product does not yet meet:

> **What is checked is the model; what is submitted is sheets.** The artifact a plan reviewer
> marks up is the drawing set, and an office that models the geometry but drafts its
> documentation in 2D over it can submit sheets that diverge from the model this system
> checked — detailing drawn on a view, a hand-typed schedule, an area table in a titleblock.
> That divergence is out of scope and unchecked, and I7 requires saying so plainly rather than
> allowing "the model complies" to be read as "the submission complies"; every report names the
> model it checked.

Half of it is already done: the report header names the model (`three_doors.ifc · Model schema
IFC4 · Engine 0.1.0`), which was itself a defect found by running the stack in Phase 2 — the
report used to name the storage key instead of the file the architect uploaded. What is missing
is the sentence that says what that naming *means*. A reader today sees a model name, three
counts and a list of findings, and nothing anywhere tells them that a clean result covers the
model and says nothing about the sheets they are about to submit.

This is the cheapest I7 obligation in the product and the one with the widest blast radius. It
is also the one place where the honest thing to write is genuinely uncomfortable, and the task
is not complete if the wording is softened into marketing.

## Scope

**Changes**

- `services/web/src/components/ReportView.tsx` — a disclosure block. T-0025 deliberately left
  room for it **above the coverage block**; that is where it goes. Coverage answers "how much
  of the rule set was evaluated"; this answers the prior question, "what artifact was evaluated
  at all", and it reads first.
- `services/web/src/i18n/en.json` and `fa.json` — the copy, both catalogues, same commit.
- `services/web/src/styles.css` — as needed. It must not be styled as a warning or an error;
  it is a statement of scope, and dressing it as an alert teaches readers to dismiss it.
- `services/web/e2e/report.spec.ts` — assert it renders, and assert its position relative to
  the coverage block in document order.

**The wording must:**

- name the model that was checked, by the filename the architect uploaded;
- state plainly that what was checked is the model and not the submitted drawing set;
- name at least one concrete way they can diverge — detailing drawn on a view, a hand-typed
  schedule, an area table in a titleblock — because an abstract disclaimer is read as
  boilerplate and a concrete one is read as information;
- never imply that the divergence is small, unlikely, or the reader's fault.

**The wording must not** be a legal disclaimer, a modal, a dismissible banner, or anything a
reader can turn off. It is part of the report.

**Does not change:** the engine, the API, the report schema, the counts, coverage, the filter.
This is presentation only. If the filename is not already on the payload, stop and say so
rather than adding a field — it is on it, and the header renders it today.

**One structural requirement.** `docs/plan.md` says this copy has to land in the generated
Markdown file as well as the view, because the file is the thing that leaves the building. The
file is **T-0032** and is not built yet. So write this copy as **one exported source that
T-0032 can consume** — not a string inlined into JSX that T-0032 will have to duplicate. Two
copies of a disclosure sentence drift, and the one that drifts is the one nobody is reading
when it does.

## How to prove it ran

```sh
make verify
make up   # rebuild: docker compose -f deploy/compose.yaml up -d --build web
make e2e
```

Evidence must show, from the rendered page in a real browser:

1. The disclosure block appears **before** the coverage block in document order — asserted on
   order, not on presence.
2. It names the uploaded model's filename, taken from the payload rather than hardcoded.
3. A screenshot you have actually opened, with the disclosure paragraph quoted verbatim from
   it in the evidence, so the wording is on the record and a later change to it is visible.
4. The i18n key list from both catalogues, and the Persian rendering — this is a paragraph of
   prose rather than a label, and it is the most likely place for an untranslated string to
   ship unnoticed.
5. Mutation proof on the document-order assertion.

## Evidence

<!-- the builder writes this -->

## Review
