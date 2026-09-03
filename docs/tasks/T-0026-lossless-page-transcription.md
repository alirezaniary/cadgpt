# T-0026 — Build lossless page evidence and ten-page model bundles

**Phase:** Regulation corpus 3   **Status:** done
**Touches invariants:** I1, import contracts

## Why

The official 43-document, 5,892-page corpus is acquired and attested, but a model still has no
stable page-addressable input. Two real Luna pilots over Volume 1 pages 11–20 disagreed on
heading and clause counts, and one pilot rewrote half of its purported exact Persian quotes.
A scan pilot initially exceeded the inference transport limit, while compressed page images
succeeded but exposed weak small-digit and clause-reference recognition. Build the deterministic
page layer first: exact source text and pixels remain evidence, models only classify and relate
stable spans, and ten-page bundles are bounded transport conveniences rather than new sources.

## Scope

- Add `cadgpt-regulations page-probe`, `transcribe`, and `transcription-check` under
  `packages/regulations`. They consume an explicit T-0025 acquisition receipt, acquisition root,
  and catalog; re-attest those inputs before reading any PDF and never mutate them.
- Account for every one of the 43 documents and all 5,892 pages. A run continues through page
  failures and records each page in a terminal `ready`, `needs_review`, or `failed` state.
  `transcription-check` fails closed on missing, duplicated, nonterminal, tampered, or unaccounted
  pages while preserving the complete report for unattended processing.
- Define strict JSON Schemas for the page manifest, per-page evidence, and ten-page bundle
  manifest. Reject unknown fields. Bind every record to catalog key, source SHA-256, 1-based PDF
  page, printed page label when observed, configuration hash, and exact parser/renderer/OCR
  versions.
- Use canonical identities derived from the attested source SHA-256 and page range. Generated
  PDF slice bytes are not an identity: the pilot proved Poppler `pdfunite` changes only the
  trailer `/ID` across identical runs. If PDF slices are emitted for convenience, make their
  bytes reproducible or explicitly exclude their digest from semantic identity. Fixed-version,
  fixed-DPI page renders and normalized text artifacts must be byte-identical across reruns.
- Preserve together, never overwrite:
  - raw native glyph text including bidi controls, presentation forms, ZWNJ, source digits,
    operators, superscripts, and line/page boundaries;
  - positioned native words/lines/blocks with page coordinates and stable span IDs;
  - normalized search text with a versioned transform log;
  - an immutable full-page source render and hashes for every derived render/crop;
  - OCR text, token/line boxes, confidence, language, preprocessing, and engine facts where OCR
    is routed.
- Normalization may apply Unicode NFKC, Persian Yeh/Kaf mapping, whitespace cleanup, and an
  explicit digit view only in a derived field. It must not silently change the raw source,
  mathematical operators, signs, decimal separators, identifiers, or clause numbering.
- Probe every page deterministically and record metrics sufficient to explain one of these
  classifications: `blank`, `native_text`, `suspect_native`, `image_scan`, `mixed`, or
  `degraded_photo`. Route each page to `none`, `native`, `ocr`, or `native_plus_ocr`; thresholds
  and their version are part of the configuration identity.
- Pin the production stack and its model data. Preferred implementation baseline:
  `docling-parse==7.16.0`, `pypdfium2==5.13.0`, Pillow, OpenCV headless, and Tesseract 5 with
  pinned `tessdata_best` `fas`, `eng`, and `osd` hashes. Add a non-root regulations Docker image
  with no runtime model downloads. A different pinned stack is acceptable only with equivalent
  positioning, rendering, reproducibility, and offline behavior proved by the real path.
- Run OCR at a resolution appropriate for small Persian digits and clause identifiers; retain a
  lower-byte model-input derivative separately. The scan pilot showed that 120-DPI JPEGs were
  readable for prose but unreliable for letter numbers and section IDs. Never promote a low-res
  model transcription to exact source evidence.
- Create ordered bundles of at most ten contiguous pages with one-page overlap only when a
  detected continuation requires it. Each bundle lists page/span IDs, raw and normalized text
  paths, stable render paths, byte totals, and continuation edges. Enforce a configurable input
  byte ceiling and provide page-by-page fallback so a retry cannot repeat the pilot's HTTP 413.
- Derive exact quotes in later stages from stored span IDs. Do not permit a model-authored string
  to claim verbatim status. The first Luna pilot produced only 20/40 normalized native-text
  matches; this layer must make that class of error structurally impossible.
- Distinguish equations, method abbreviations, units, and prose mentions in the page evidence.
  This task preserves symbols, text, coordinates, and source crops but does not interpret,
  convert, or validate equations. `LRFD` and `ASD` are abbreviations, not formulas.
- Store generated page data outside Git beneath a caller-created output root. Apply the same
  no-symlink, regular-file, ownership, no-clobber, content-addressed-history, and re-attestation
  discipline established by T-0025. Reuse matching artifacts and recover owned interrupted
  writes without blocking unattended completion.
- Add only narrow ignores for generated output. Never commit PDFs, page images, OCR/model data,
  transcription receipts, Luna responses, or temporary benchmarks.
- Keep all network and inference out of `cadgpt_engine`. Do not call Luna, crawl the web, infer
  document hierarchy, extract semantic rules, translate clauses, generate IDS, or decide legal
  applicability in this task.

## Tests

- A fixture corpus covers native RTL Persian text, Arabic presentation forms, ZWNJ, Persian and
  Latin digits, an image-only scan, mixed text/image content, watermarking, rotation, blank pages,
  a cross-page sentence, a table-like page, and mathematical symbols.
- Page counts and page identities exactly cover each fixture and reject missing, duplicate,
  reordered, out-of-range, extra, or source-hash-drifted records.
- Raw text is byte-preserved; normalized text has a deterministic transform log and cannot alter
  the raw value. Clause numbers, signs, operators, superscripts, and both digit forms survive.
- Native, OCR, and native-plus-OCR routes execute real parser/renderer/OCR binaries. Do not mock
  the transcription functions themselves.
- Fixed configuration produces byte-identical canonical manifests, positioned text, and renders
  on two clean runs; the second run reuses artifacts without changing mtimes.
- Generated ten-page bundles preserve order and boundaries, identify continuations, obey the byte
  ceiling, and fall back to smaller/page inputs instead of failing the whole document.
- Symlink, FIFO, traversal, extra-entry, partial-write, tool-crash, corrupt-PDF, and OCR-timeout
  cases all reach stable terminal states and make `transcription-check` fail closed.
- Import contracts prove regulations remain beside the engine and no network/inference package
  enters `cadgpt_engine`.

## How to prove it ran

```sh
make verify

transcription_root=$(mktemp -d /tmp/cadgpt-inbr-transcription.XXXXXX)

uv run cadgpt-regulations page-probe \
  --acquisition /tmp/cadgpt-inbr-acquisition.GzxDl0/acquisition.json \
  --root /tmp/cadgpt-inbr-acquisition.GzxDl0 \
  --output-root "$transcription_root"

uv run cadgpt-regulations transcribe \
  --probe "$transcription_root/page-probe.json" \
  --root "$transcription_root"

uv run cadgpt-regulations transcription-check \
  "$transcription_root/transcription.json" \
  --root "$transcription_root" \
  --acquisition-root /tmp/cadgpt-inbr-acquisition.GzxDl0
```

The evidence must show:

- 43/43 documents and 5,892/5,892 pages have exactly one terminal probe and transcription record;
- page-classification and route counts, OCR language/model hashes, failures, and review flags;
- all source PDFs remain unchanged and every page/render/text artifact re-attests;
- Volume 1 pages 11–20 preserve the 30 printed heading IDs and exact source spans without
  model-written quotations;
- all three photographed clarification pages are routed as scans, page 2 is retained despite
  being routing-only, and small identifiers remain separately reviewable rather than guessed;
- at least one watermarked page, one mixed page, one formula-bearing page, and one table-bearing
  page retain source renders and positioned evidence;
- a second full run produces the same canonical manifest and reuses every matching artifact
  without rewriting it;
- generated model bundles cover the corpus in ordered ranges of at most ten pages and satisfy the
  configured byte ceiling.

If OCR or rendering fails, the command still finishes all documents and records terminal page
failures. The task is not done until full-corpus accounting is proved; failed or review pages may
remain ineligible for semantic publication without stopping later experimental extraction.

## Evidence

`make verify` passed on 2026-09-03 with pnpm activated through a temporary Corepack shim.
Ruff and its format check passed over 195 files, strict mypy passed over 160 source files,
all seven import contracts were kept, pytest reported `273 passed`, and frontend lint,
typecheck, and production build passed. The full regulations test suite and the focused
39-test storage/probe/transcription suite also passed.

Real transcription root: `/tmp/cadgpt-inbr-transcription.hwIllI`

```text
$ uv run cadgpt-regulations page-probe \
    --acquisition /tmp/cadgpt-inbr-acquisition.GzxDl0/acquisition.json \
    --root /tmp/cadgpt-inbr-acquisition.GzxDl0 \
    --output-root /tmp/cadgpt-inbr-transcription.hwIllI \
    --render-dpi 400 \
    --tessdata /tmp/cadgpt-tessdata-best \
    --workers 8 \
    --page-timeout 300
wrote deterministic page probe:
/tmp/cadgpt-inbr-transcription.hwIllI/manifests/page-probe/
b7ea22694d62999e840d5ca06203bcc8a255cbc9a3cfa44133aeaac16e94ac5b.json
pages 4492 ready, 1400 need review, 0 failed; packages 5892 created, 0 reused

$ uv run cadgpt-regulations transcribe \
    --probe /tmp/cadgpt-inbr-transcription.hwIllI/manifests/page-probe/b7ea22694d62999e840d5ca06203bcc8a255cbc9a3cfa44133aeaac16e94ac5b.json \
    --root /tmp/cadgpt-inbr-transcription.hwIllI \
    --tessdata /tmp/cadgpt-tessdata-best \
    --workers 8 \
    --ocr-timeout 300
wrote deterministic transcription:
/tmp/cadgpt-inbr-transcription.hwIllI/manifests/transcription/
e32885cd587661f1876680b9ac45da2d82693a3482e419fb56fed042100b8501.json
pages 938 ready, 4954 need review, 0 failed; packages 5892 created, 0 reused;
bundles 663 created, 0 reused

$ uv run cadgpt-regulations transcription-check \
    /tmp/cadgpt-inbr-transcription.hwIllI/manifests/transcription/e32885cd587661f1876680b9ac45da2d82693a3482e419fb56fed042100b8501.json \
    --root /tmp/cadgpt-inbr-transcription.hwIllI \
    --acquisition-root /tmp/cadgpt-inbr-acquisition.GzxDl0
wrote transcription check:
/tmp/cadgpt-inbr-transcription.hwIllI/checks/transcription/
02f96fbb1de7e596b736c7a9fecadc5f5d03b74b358609b34ec6cf5e558f7679.json
observed 43 documents and 5892 pages; 0 blocker(s)
```

The probe accounted for all 43 documents and 5,892 pages. It classified 22 blank, 13
degraded-photo, 3,424 image-scan, 137 mixed, 909 native-text, and 1,387 suspect-native
pages. Routes were 909 native, 3,437 OCR, 1,524 native-plus-OCR, and 22 none. The
transcription retained 4,961 OCR-bearing pages; `needs_review` is therefore common and is
an explicit eligibility state rather than a missing or guessed transcription. The check
re-attested the T-0025 acquisition, every probe package, transcription artifact, bundle,
manifest, and index with zero blockers, so the 43 source PDFs remain unchanged.

The production OCR identity is Tesseract 5.3.4 with `tessdata_best` commit
`e12c65a915945e4c28e237a9b52bc4a8f39a0cec`. Model SHA-256 values are
`99e420969b5ddd2cb135b416316a7ed417c59c4faf9e0d28941348f6448114df` for `fas`,
`8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba` for `eng`, and
`9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff` for `osd`.

Volume 1 PDF pages 11-20 are all `ready` native pages. Excluding the repeated running
header, their native positioned lines contain exactly 30 observed printed heading IDs and
30 unique stable span IDs in source order. Exact glyph text, including presentation forms
and original spacing, remains in the immutable native layouts; later stages need not accept
a model-written string as a verbatim quote.

All three pages of `volume-12-supervisor-clarification-1404` are retained as image scans,
routed to OCR, and marked for review with low-confidence identifier and signature-region
flags. Page 2 is present rather than dropped as routing-only material; its grayscale 400-DPI
PSM 3 result retained 117 tokens across 15 lines. Visual inspection confirmed the stored
model render is the official cover-letter/routing page.

Volume 17 page 20 retains the visible diagonal `www.inbr.ir` watermark. It was routed as an
image scan, processed with grayscale plus Otsu thresholding, retried from PSM 3 to PSM 6,
and kept under `OCR_WATERMARK_OVERLAP_REVIEW` rather than treating watermark text as a
trusted rule. The source render and both preprocessing/result identities re-attest.

The corpus contains 3,571 equation candidates across 1,340 pages, 7,192 unit mentions, 350
method-abbreviation candidates, and table evidence on 747 pages. A visually inspected mixed
page, `guide-masonry-perimeter-walls-v3-1404` PDF page 34, preserves native and OCR layouts,
the native expression `𝑀𝑑1 = 𝜙`, its stable source span and
formula crop, and a table-like-region hint. Candidate types remain distinct and no equation
meaning is inferred in this task.

All 663 bundles use the bounded-bundle fallback, cover 5,892 unique pages, contain at most
10 pages, and remain below the 8 MiB ceiling. The largest bundle is 3,218,164 bytes. The
6,447 total page slots include 555 deliberate overlap slots connected by recorded
continuation edges.

The complete second run returned the same canonical manifests with `0 created, 5892 reused`
page packages and `0 created, 663 reused` bundles. Before and after both reuse runs, the
61,298 generated files had the identical ordered path/mtime/size digest
`29f3ffd391f10af007fd968e43ea94a3e313597f20aa93755d6341d16fa4db5f`.
No evidence artifact was rewritten.

The non-root offline Docker image is
`sha256:2d37e733104fb9ce7c565a961dc7185a6ca6d28b88d0942bd79b7dd36c7724f0`.
It starts with network disabled as UID/GID 10001, exposes the regulations CLI, reports
Tesseract 5.3.4, and lists only the pinned `eng`, `fas`, and `osd` data. No PDF, render,
OCR output, model bundle, manifest, check report, or Luna response is tracked in Git.

## Review

Required because this task establishes the evidence boundary consumed by model extraction and
touches I1/import contracts.
