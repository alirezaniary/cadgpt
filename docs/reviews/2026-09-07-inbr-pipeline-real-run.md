# Review — INBR transcription pipeline, real run on the official corpus

**Branch:** `feat/inbr-regulations-pipeline` at `dc435cd` ("refactor piplene")
**Method:** ran the real path end to end against the durable workspace, not the test suite.
**Workspace:** `.cadgpt/inbr/` (ignored), cohort `revision-2026-09-07`.

## Gate status

| Gate | Result |
| --- | --- |
| `ruff` | pass |
| `mypy --strict` (166 files) | pass |
| `import-linter` | 7 contracts kept, 0 broken |
| `pytest` (whole repo) | 299 passed |
| `make verify` | **fails** — `web-verify` lints the untracked `services/web/storybook-static/` build output. Unrelated to this branch; delete or ignore that tree. |

The Python suite is green while three of the five pipeline stages are broken on real input.
That is the failure mode `CLAUDE.md` warns about, and it recurred here.

## What actually works

**Stage 1 — acquisition. Verified.**

```
acquired 43; reused 0; pages 5892; bytes 470674872; quarantined 0
valid acquisition: 10/10 metadata, 43/43 PDFs, 5892 pages, 470674872 bytes
```

Byte total matches the `2026-09-06` decision-log pin exactly. `trust_env=False` on the httpx
client is correct and necessary — the shell's `HTTPS_PROXY=http://127.0.0.1:2080` gets a
Cloudflare 403 from `inbr.ir`; the direct connection returns 200.

**Stages 2–3 — probe, transcribe, structure. Run to completion on a native-text volume.**
Volume 1 pages 1–40: 40 ready, 0 failed; 5 bundles; 2801 nodes, 22 tables, 2 units. Persian
text comes out legible and correctly ordered after normalization.

## Findings

### F1 — `extract-jobs` crashes on every invocation (blocker, regression in `dc435cd`)

`_structure_binding` (`extraction_jobs.py:369`) builds its return dict with
`pages, nodes, formulas, tables, bundles` — no `units`. `_bundle_structure_binding`
(`extraction_jobs.py:430`) then reads `value["units"]`. Unconditional `KeyError`, surfaced as
a raw traceback rather than an `ExtractionJobError`.

```
File "packages/regulations/src/cadgpt_regulations/extraction_jobs.py", line 430
    for item in cast(list[JsonObject], value["units"])
KeyError: 'units'
```

Both functions were added in `dc435cd`. Reproduced on the good Volume 1 structure and on a
degenerate one — it is not input-dependent. Stage 4 has never run, and stage 5
(`semantic-publish`) consumes `jobs.json`, so it is unreachable too.

No test in `test_extraction_jobs.py` calls `build_structured_extraction_jobs` with a real
structure manifest; the only structure-aware test mutates `manifest["structure_sha256"]` on a
prebuilt manifest. That is why 299 tests pass over a function that cannot execute.

### F2 — a relative `--output-root` fails all 5,892 pages with a misleading error (blocker)

`tempfile.mkdtemp()` returns `os.path.abspath(...)` unconditionally. `_install_package`
(`page_probe.py:879`) creates the temporary directory under `destination.parent`, but when the
caller passed a relative root, `destination` stays relative while `temporary` comes back
absolute, so `install_terminal_directory` (`storage.py:504`) rejects them as non-siblings.

Observed: every page of a 40-page probe failed with
`TranscriptionError: temporary and terminal package directories must be siblings`, and the run
then died on an inventory mismatch listing empty package directories — a diagnostic that points
nowhere near the cause. The same command with `$PWD/...` succeeded 40/40.

`docs/inbr-operations.md` happens to use `$PWD`, which is the only reason this was not hit
earlier. Normalise the root with `Path.resolve()` at the CLI boundary (or compare resolved
parents in `install_terminal_directory`).

### F3 — clause identifiers are lost or truncated; the hierarchy is fabricated (blocker for the product)

Ground truth for Volume 1 PDF page 16, from `pdftotext`: `2-5-1-1`, `6-1-1`, `1-6-1-1`.

What the graph recorded:

| raw line from docling | true clause | `printed_label` | `kind` |
| --- | --- | --- | --- |
| `"  2  -5  -1  -1"` | `2-5-1-1` | `None` | `paragraph` |
| `"  6  -1-1"` | `6-1-1` | `None` | `paragraph` |
| `"  1-6  -1  -1"` | `1-6-1-1` | `1-6` | `section`, `parent_id: None` |

The PDF draws each digit group as a separate text run, so the native line text carries interior
spaces. `_LABEL_PATTERN` (`structure.py:33`) requires `[-.]` with no surrounding whitespace and
is matched against `raw_text`, not `normalized_text`, so it either fails outright or captures a
prefix.

Measured over the 40 probed pages: **174 clause-identifier lines → 19 correct, 8 truncated,
147 label lost entirely.** ~11% correct, and several of the 19 are false positives (below).

Consequences: `_node_kind` derives depth from the captured label, so `1-6-1-1` is filed as a
depth-2 `section` and `_node_parent` re-roots it at `parent_id: None`, resetting the parent
stack mid-document. The 2,773 `paragraph` nodes hang off a hierarchy that does not correspond
to the document. Every downstream rule cites `source_node_id`, so this poisons the semantic
layer at its anchor.

### F4 — running headers, ISBN, and the cover price become headings

`_LABEL_PATTERN` matches any line starting with a dash-separated numeric run, with no test for
whether the line is a heading (short line, distinct bbox, page position). Actual `section` /
`subclause` nodes in the graph:

- `978-600-301-002-4` — the ISBN, filed as `subclause` (depth 5)
- `30.000` — the cover price, filed as `section`
- `1-1` — the running page header, re-emitted as a root `section` on pages 11, 13, 15, 17, 19,
  21, 23, 25, …

Each of these resets the parent stack.

### F5 — `transcription-check` reports "0 blockers" when 100% of pages failed (fail-open gate)

Volume 13 pages 40–80 route entirely to OCR. With no Tesseract present:

```
transcribe ......... pages 0 ready, 0 need review, 41 failed; bundles 5 created
transcription-check  observed 1 documents and 41 pages; 0 blocker(s)      exit 0
structure            accounted 1 documents and 41 pages; 0 nodes, 0 tables, 0 formulas, 0 units
structure-check      valid structure: 1 documents, 41 pages, 0 formula candidates       exit 0
```

`transcribe` still wrote 5 content-addressed bundles with `input_bytes: 0` and
`page_count: 10`. Nothing in the chain treats "every page failed" as a blocker; the check
report carries `pages_failed: 41` in its summary and `blockers: []` beside it. An operator
following `docs/inbr-operations.md` reads two green lines and advances.

The doc's advice to read the printed counts is correct but is the only defence. `pages_failed
> 0` should be a blocker, and empty bundles should not be built.

### F6 — the corpus cannot be transcribed in this environment

- `tesseract` is **not installed**. `page_tools.py:25` pins exactly `tesseract 5.3.4`, and
  `_PINNED_TESSDATA_BEST` pins the `fas`/`eng`/`osd` `tessdata_best` model hashes. Ubuntu
  24.04 ships `5.3.4-1build5`, so the pin is satisfiable, but the models must be fetched
  separately.
- **17 of the 43 PDFs have no embedded text at all** in their first 20 pages, so they route to
  `ocr`. Volume 13 is `suspect_native` on 41/41 sampled pages → `native_plus_ocr`. Roughly
  half the corpus is OCR-dependent.

Operational trap: `toolchain_sha256` is a path component of every page package and currently
hashes `"tesseract": null`. Installing Tesseract later changes that hash and orphans every
package already written. **Install Tesseract and the pinned `tessdata_best` models before the
first `page-probe`,** not between stages.

### F7 — `native_plus_ocr` now discards the native text layer (unexercised, from `dc435cd`)

`_page_lines` (`structure.py`) previously returned `[*native_lines, *ocr_lines]` for this
route. It now returns `ocr_lines` only, justified in a comment as "the probe marked the native
layer incomplete". That holds for `suspect_native` (<20 native chars). It does not hold for
`mixed`, which is `chars >= 20` **and** `bitmap_coverage >= 10%` and is classified `ready` with
reason `NATIVE_TEXT_AND_LARGE_BITMAP` — a page with good embedded text next to a figure. For
those pages the accurate native text is dropped in favour of OCR of a render.

Not exercised: the sampled documents produced 0 `mixed` pages. Flagging on inspection only.
Note that Volume 17's local name is `mabhas17-watermark-...`; a full-page watermark bitmap
would push otherwise-clean text pages into `mixed`.

### F8 — `method_abbreviation` candidates are silently dropped; `figure` is a schema kind nothing produces

`transcription.py:853` emits `method_abbreviation` candidates (e.g. "LRFD", "ASD" mentions).
`structure.py:374-382` only branches on `kind == "equation"` and `kind == "unit_mention"`; any
`method_abbreviation` candidate is read off the page evidence and never appended to `formulas`,
`units`, or any other list. No diagnostic, no `needs_review` flag — it vanishes, and nothing in
`validate_structure` checks that every upstream candidate kind landed somewhere, so the loss is
undetectable from the manifest alone.

Separately, `source-graph.schema.json:127` lists `"figure"` as a valid node kind, but no stage
between transcription and structure (`transcription.py`, `page_tools.py`) ever emits a figure
candidate. It is a schema entry for a feature that does not exist yet, not a bug in the strict
sense, but worth closing before anyone assumes figures/captions are anchored.

### Note — why F3/F4 survived 299 green tests

`test_structure.py` has 4 tests (formula record, unit record, schema-rejection, alternate-line
alignment). None call `build_structure()` or `_build_document_graph()` — the label→depth→kind
heuristic that produces F3 and F4 is exercised by zero tests. Same failure shape as F1: the
function that breaks on real input is never invoked by the suite that passed.

## Suggested order

1. F1 — add `"units": graph.get("units", [])` to `_structure_binding`, and a test that runs
   `extract-jobs` against a real structure manifest.
2. F2 — resolve roots at the CLI boundary.
3. F5 — make `pages_failed > 0` a blocker; stop emitting empty bundles.
4. F3 / F4 — the real design work. Label extraction needs whitespace-tolerant matching against
   normalized text plus a positional/typographic heading test. Worth its own task file.
5. F6 — provision Tesseract 5.3.4 + `tessdata_best` before any further probing.
6. F7 — decide whether `mixed` keeps both layers.
7. F8 — route `method_abbreviation` candidates somewhere real or drop the kind explicitly; add a
   `figure` producer or remove it from the schema until one exists.

## Artifacts on disk

- `.cadgpt/inbr/acquisition/revision-2026-09-07/` — the full attested 43-PDF corpus. Keep.
- `.cadgpt/inbr/transcription/revision-2026-09-07/` — Volume 1 pp. 1–40 (good), Volume 13
  pp. 40–80 (all failed, kept as F5 evidence).
- `.cadgpt/inbr/structure/` — Volume 1 graph, the basis for the F3/F4 counts.
- `.cadgpt/inbr/structure2/`, `.cadgpt/inbr/extraction2/` — degenerate-case scratch. Disposable.
