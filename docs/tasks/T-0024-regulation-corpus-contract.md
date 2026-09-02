# T-0024 — Establish the regulation corpus contract and inventory

**Phase:** Regulation corpus 1   **Status:** done
**Touches invariants:** I1, import contracts

## Why

The INBR corpus is now a real project input: 42 local downloads comprising 41 parseable
PDFs and one HTML page saved with a `.pdf` suffix. Before OCR or model extraction, the build
needs a deterministic inventory that preserves source identity, official ordering, English
title metadata, document relationships, and every failure. This task creates the independent
package and contract that all later OCR, Luna, validation, and publication stages must obey.

Human review must not block this or later batch stages. Uncertain records are marked
`needs_review` or `quarantined`, remain present in coverage output, and are excluded from a
publishable release until resolved.

## Scope

- Create a new uv workspace package at `packages/regulations/`, importable as
  `cadgpt_regulations`, with a `cadgpt-regulations` CLI. It must remain separate from
  `cadgpt_engine` and Django.
- Extend root lint, strict-mypy, pytest, and import-linter configuration so the new package is
  covered by `make verify`. Add an import contract forbidding either regulations code or the
  checking engine from importing the other. The regulations package may acquire network and
  inference adapters in later tasks; neither may ever leak into `cadgpt_engine`.
- Add strict JSON Schemas for the corpus catalog and generated inventory manifest. Reject
  unknown fields. Schema/version changes must be explicit.
- Add curated INBR catalog data covering the 24 ordered code-volume families and all local
  supplemental documents. Preserve Persian titles and original filenames; add English titles
  with `official`, `cover_translation`, or `curated` provenance rather than renaming files.
- Record document kind, catalog order, volume, edition/year where evidenced, legal status,
  and directed relationships. At minimum support `EDITION_OF`, `APPENDIX_OF`,
  `MANDATORY_APPENDIX_OF`, `AMENDS`, `CLARIFIES`, `SUPERSEDES`, `GUIDE_FOR`, `DRAFT_OF`,
  `REFERENCES`, and `EXPLAINS`.
- Encode the nine ordered Volume 19 appendices as children of Volume 19; the protective
  requirements document as a mandatory appendix to Volume 4; the borehole circular as an
  amendment to Volume 7; the dated Volume 11 document as an amendment/clarification; the
  CamScanner circular as a clarification related to Volume 12; and Amendment No. 1 as an
  amendment to Volume 17. Supplementary guides must not be classified as numbered volumes or
  binding regulations without evidence.
- Use the current official catalog and REST record as catalog provenance:
  `https://inbr.ir/مباحث-مقررات-ملی/` and
  `https://inbr.ir/wp-json/wp/v2/pages/5825`. Retain the historical bilingual provenance
  endpoints `https://inbr.ir/wp-json/wp/v2/pages/1160` and
  `https://inbr.ir/wp-json/wp/v2/pages/104`. This task stores provenance; it does not need a
  recurring network crawler yet.
- Implement inventory over an arbitrary directory using safe Unicode paths and no filename
  derivation from decoded URL path separators. For every file, calculate SHA-256 and byte
  size, inspect magic bytes/content rather than trusting the suffix, and obtain authoritative
  PDF page counts with `pdfinfo`.
- A malformed, mislabeled, encrypted, unreadable, or unsupported file must still appear in
  the manifest with a stable error code, diagnostic, and terminal `quarantined` state. The
  command continues across other files and reports complete coverage.
- The generated manifest must be deterministic for identical inputs and catalog/configuration.
  Do not include an implicit wall-clock timestamp in content identity.
- The manifest records, at minimum: original filename, catalog key/order, SHA-256, bytes,
  detected media type, artifact state, PDF page count when available, Persian/English title,
  translation provenance, edition/publication metadata, legal status, relationships,
  source URLs, evidence/provenance, and review flags.
- Add a manifest validation/publish-gate command. Schema-valid quarantined content is valid as
  an inventory, but the publish gate must fail while any expected artifact is missing,
  unaccounted, nonterminal, or quarantined.
- Add real tests for deterministic ordering/hashing, Persian filenames, MIME-mismatched HTML,
  `pdfinfo` failure, catalog relationships, schema rejection, complete coverage, and the
  distinction between successful inventory and failed publication readiness.
- Keep `docs/inbr/` unchanged and do not commit the 449 MiB source corpus. Add narrowly scoped
  ignores for local source/artifact payloads if needed; do not ignore curated catalogs,
  schemas, tests, or task evidence.
- Update `docs/stack.md` for any dependency introduced. Do not add OCR, OpenAI, database, or
  service integration in this task.

## How to prove it ran

Run the complete repository gate:

```sh
make verify
```

Then execute the real CLI over the actual corpus and write outside the repository:

```sh
uv run cadgpt-regulations inventory docs/inbr --output /tmp/inbr-manifest.json
uv run cadgpt-regulations validate /tmp/inbr-manifest.json
uv run cadgpt-regulations publish-check /tmp/inbr-manifest.json
```

The evidence must show:

- 42 files accounted for, 41 valid PDFs, one quarantined MIME mismatch, and 5,749 PDF pages;
- `راهنمای-طراحی-دیوارهای-بنایی-محوطه.pdf` identified as HTML rather than accepted as PDF;
- all 24 numbered volumes represented in canonical order;
- nine ordered Volume 19 appendix relations and the other required amendment/appendix links;
- `inventory` and `validate` succeed without waiting for human input;
- `publish-check` exits non-zero and names the quarantined artifact, proving unsafe data cannot
  be published silently;
- running inventory twice produces byte-identical JSON and the same SHA-256.

## Evidence

`make verify`: passed on 2026-09-02 with the documented `.env.example` values exported and
the repository's pinned pnpm activated through a temporary Corepack shim. Ruff passed, strict
mypy passed over 149 source files, all seven import contracts were kept, pytest reported
`193 passed`, and the frontend lint, typecheck, and production build passed.

Real path:

```text
$ uv run cadgpt-regulations inventory docs/inbr --output /tmp/inbr-manifest.json
wrote deterministic manifest: /tmp/inbr-manifest.json
accounted 42/42 expected artifacts across 42 files
valid PDFs 41; PDF pages 5749; quarantined 1; missing 0; unaccounted 0

$ uv run cadgpt-regulations validate /tmp/inbr-manifest.json
valid manifest: 42 files, 41 valid PDFs, 5749 PDF pages, 1 quarantined

$ uv run cadgpt-regulations publish-check /tmp/inbr-manifest.json
not publishable: 2 blocker(s)
- راهنمای-طراحی-دیوارهای-بنایی-محوطه.pdf: MEDIA_TYPE_MISMATCH: expected application/pdf, detected text/html
- دستور-کار-ارزیابی-ایمنی-و-بهسازی_photo.pdf: NEEDS_REVIEW: PUBLICATION_METADATA_UNRESOLVED
exit 1
```

The manifest accounts for `470439080` source bytes. The quarantined HTML artifact is 53,677
bytes, SHA-256
`896389209a92153e613165fc21b4a1daa4b758e793cad40dab2c25b03a8f56fd`, has detected type
`text/html`, and has no PDF page count. No source file under `docs/inbr/` was changed.

The inventory was run a second time at `/tmp/inbr-manifest-second.json`; `cmp` returned 0 and
both files had SHA-256
`bf303f2157c15711cfc5182409b266645428e7e8c9c20aab742d72d6920a4aba`.
All 42 curated records matched their pinned approved SHA-256 values; there were zero
`SOURCE_HASH_MISMATCH` records. Tests prove a structurally valid PDF placed under a known
official filename is quarantined with `SOURCE_HASH_MISMATCH`, receives no PDF page count, and
cannot pass publication unless its exact bytes are explicitly approved by the catalog.

Catalog evidence from the generated manifest showed numbered volumes exactly
`[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24]`, Volume 19 appendix
orders exactly `[1,2,3,4,5,6,7,8,9]`, and these required links:

```text
volume-04-protective-security-appendix-1403 MANDATORY_APPENDIX_OF volume-04-edition-1396
volume-07-borehole-amendment-1405 AMENDS volume-07-edition-1400
volume-11-amendment-1403-08-08 AMENDS volume-11-edition-1400
volume-11-amendment-1403-08-08 CLARIFIES volume-11-edition-1400
volume-12-supervisor-clarification-1404 CLARIFIES volume-12-edition-1392
volume-17-amendment-01 AMENDS volume-17-edition-1403
```

The official-record check corrected an upstream audit mix-up before it entered the catalog:
post 6691 is the explicitly non-citable Volume 22 second-edition draft; posts 7064 and 5713
are current and draft provenance for the protective/security appendix respectively. Post 7061
is the current Volume 24 download and post 6022 its earlier non-citable draft.

Wheel/resource path:

```text
$ uv build --package cadgpt-regulations --out-dir /tmp/cadgpt-regulations-dist
Successfully built cadgpt_regulations-0.1.0.tar.gz
Successfully built cadgpt_regulations-0.1.0-py3-none-any.whl
$ uv run --isolated --with /tmp/cadgpt-regulations-dist/cadgpt_regulations-0.1.0-py3-none-any.whl python <resource probe>
wheel resources: 24 families, 42 artifacts, 42 pinned hashes
```

Wiring: root `pyproject.toml` now contains
`cadgpt-regulations = { workspace = true }`, includes `cadgpt-regulations` in the dev group,
adds `packages/regulations/tests` to pytest, and registers `cadgpt_regulations` as an import
root. The enforced boundary is:

```toml
[[tool.importlinter.contracts]]
name = "Regulation acquisition and checking engine are independent"
type = "independence"
modules = ["cadgpt_regulations", "cadgpt_engine"]

[[tool.importlinter.contracts]]
name = "Regulation corpus core has no service or framework dependencies"
type = "forbidden"
source_modules = ["cadgpt_regulations"]
forbidden_modules = ["cadgpt", "django", "rest_framework", "celery"]
```

## Review

**Verdict:** Fix Now findings remediated. Queue Later items remain outside this task as
directed; no second review was requested.

- Every curated artifact now carries a strict `expected_sha256`. Inventory compares the
  calculated source digest before PDF processing, emits terminal `SOURCE_HASH_MISMATCH` for
  substituted bytes, and manifest validation prevents that mismatch from being relabeled
  ready. The real corpus produced 42/42 approved hash matches.
- Manifest writes now use an exclusive randomized temporary file in the destination directory,
  flush and fsync it, reject symlink or non-regular output hazards, and atomically replace the
  destination. The reproduced `.manifest.json.tmp` symlink attack leaves its target unchanged.
- Unsupported accepted guide relationships were removed from the damper/isolator draft,
  masonry perimeter-wall guide, and structural calculation/design draft. Their legal status
  remains explicitly non-binding; relationships can be restored only with document evidence.
- A seventh import contract now prevents `cadgpt_regulations` from importing the Django
  service or `django`, `rest_framework`, and `celery`, while the existing independence contract
  continues to isolate it from `cadgpt_engine` in both directions.
