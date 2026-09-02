# T-0025 — Acquire and attest the official INBR corpus

**Phase:** Regulation corpus 2   **Status:** done
**Touches invariants:** I1, import contracts

## Why

T-0024 pins the bytes already present locally, but the corpus cannot yet be reproduced from
official sources. Its filename field also conflates remote identity with a safe filesystem
path, and the masonry perimeter-wall landing page was downloaded as HTML even though it links
two real versioned PDFs. Add a bounded, official-source-only acquisition stage that snapshots
provenance, downloads and attests every artifact, records every failure, and completes without
waiting for human input.

## Scope

- Add `cadgpt-regulations acquire` and `cadgpt-regulations acquisition-check`.
  `acquire` must process all configured metadata sources and artifacts to terminal states,
  without prompting or stopping at the first failure. `acquisition-check` fails closed if any
  required source or artifact is missing, nonterminal, quarantined, or different from its
  pinned contract.
- Fix the queued custom-catalog defect: `inventory --catalog` must use the supplied catalog for
  both construction and immediate validation. `inventory`, `validate`, `publish-check`,
  `acquire`, and `acquisition-check` must consistently honor the same explicit catalog.
- Version the catalog and manifest contracts to distinguish:
  - `download_url`: the configured official URL requested for an artifact;
  - `remote_filename`: the exact inert remote name, Unicode preserved, which may contain
    decoded separators and is never passed to filesystem APIs;
  - `local_path`: a unique catalog-controlled flat relative path used for storage/inventory;
  - acquisition receipt `requested_url` and final `resolved_url`.
- Never derive `local_path` from a decoded URL or `Content-Disposition`. Reject absolute paths,
  slash or backslash separators, dot components, NULs, duplicates, symlinks, non-regular
  targets, and any path escaping the output root.
- Restrict acquisition to configured HTTPS INBR origins and validate every redirect hop. Do
  not recursively crawl, use search engines, follow unrelated links, or execute fetched
  content. HTTP bodies are untrusted data.
- Download with bounded timeouts and retries into unpredictable exclusive temporary files in
  the destination directory. Stream and hash before atomic installation. Never overwrite a
  differing existing artifact; verify and reuse an identical artifact idempotently.
- Require a successful HTTP response, approved origin chain, PDF magic, pinned SHA-256,
  expected byte/page facts where declared, and successful `pdfinfo`. Preserve rejected payloads
  only under content-addressed quarantine paths with stable diagnostics.
- Add a strict acquisition-receipt JSON Schema covering catalog identity, metadata snapshots,
  artifact results, requested/resolved URLs, remote/local names, hashes, byte counts, detected
  media, page counts, attempts, stable errors, terminal states, and complete summary counts.
  Identical official responses and configuration must produce deterministic receipt content;
  retrieval time may be recorded outside content identity.
- Snapshot these official WordPress records: pages 104, 1160, and 5825; posts 5713, 6022,
  6691, 6735, 7061, and 7064. Retain raw bytes content-addressed by SHA-256 and a canonical
  projection containing WordPress ID, status, dates, link, rendered title, rendered content,
  and extracted document links.
- Compare each canonical projection and discovered-link set against the curated catalog.
  New, missing, duplicate, relabeled, or remapped links become terminal
  `SOURCE_DISCOVERY_DRIFT`; acquisition never edits or self-approves catalog metadata.
- Replace the quarantined masonry HTML artifact in the curated artifact set with the two PDFs
  linked by official post 6735, preserving post order:
  - Version 3 / 1404: remote `دستورالعملطراحی.pdf`, local
    `guide-masonry-perimeter-walls-v3-1404.pdf`, 68 pages, 3,845,085 bytes,
    SHA-256 `acd530ac4b887bdf4924aa614d901becf9d06c95717f6a1934005ff9316447a3`.
  - Version 2 / 1403: remote `طراحی-دیوار-محوطه-مهر-1403.pdf`, local
    `guide-masonry-perimeter-walls-v2-1403.pdf`, 75 pages, 5,217,505 bytes,
    SHA-256 `f1eb68785aa4abb57b537f06c850ec67b8344355ef0fce4f12aadb194f8f773c`.
  Both remain non-binding guides. Add `SUPERSEDES` only when the official post/version evidence
  establishes it. Add `GUIDE_FOR volume-08` only if explicit official or document evidence is
  stored; otherwise retain that relationship as `needs_review`, never accepted.
- For Volume 17 explicitly separate the inert remote name
  `mabahse/mabahse17/mabhas17-watermark-1403-02.pdf`, the official URL retaining `%2F`, and
  the safe local path `mabahse_mabahse17_mabhas17-watermark-1403-02.pdf`.
- Keep review status independent from acquisition health. A `needs_review` artifact may be
  fully acquired and transcribed later, while remaining ineligible for publication.
- Keep `docs/inbr/` unchanged. Commit no downloaded PDFs, metadata response bodies, quarantine
  payloads, or live acquisition receipts. Add narrowly scoped ignores for generated acquisition
  storage and update stack/decision documentation for any dependency and the identity model.
- Do not add OCR, layout analysis, Luna calls, semantic extraction, scheduling, Django, or
  checking-engine integration.

## Tests

Use a real local HTTP server and real minimal PDFs so redirect handling, streaming, hashing,
atomic installation, and `pdfinfo` execute. Mocking the acquisition functions themselves is
not evidence.

- A materially different custom catalog works through every CLI stage and fails when omitted.
- Redirects record requested/final URLs and reject any unapproved hop or origin.
- Encoded remote separators and `Content-Disposition` never control local storage paths.
- Masonry post fixtures resolve exactly the ordered version 3 and version 2 PDF links.
- Missing, unexpected, duplicate, or relabeled landing-page links produce discovery drift.
- Metadata snapshots are content-addressed and tampering fails `acquisition-check`.
- HTML, hash, size, page-count, and origin mismatches are quarantined without stopping siblings.
- A conflicting existing target is never overwritten; an identical target is verified/reused.
- Symlink, non-regular, traversal, partial-write, timeout, and retry-exhaustion cases terminate
  safely with stable error codes.
- One failed download still produces complete terminal coverage for every configured source.
- Any quarantine/nonterminal record makes `acquisition-check` fail.

## How to prove it ran

```sh
make verify

inbr_acq_root=$(mktemp -d /tmp/cadgpt-inbr-acquisition.XXXXXX)
uv run cadgpt-regulations acquire \
  --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json \
  --output-root "$inbr_acq_root"

uv run cadgpt-regulations acquisition-check \
  "$inbr_acq_root/acquisition.json" \
  --root "$inbr_acq_root" \
  --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json

uv run cadgpt-regulations inventory \
  "$inbr_acq_root/artifacts" \
  --output "$inbr_acq_root/manifest.json" \
  --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json

uv run cadgpt-regulations validate \
  "$inbr_acq_root/manifest.json" \
  --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json

uv run cadgpt-regulations publish-check \
  "$inbr_acq_root/manifest.json" \
  --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json
```

The evidence must show:

- all nine official metadata records snapshotted, validated, and hashed;
- 43/43 artifacts acquired as valid approved PDFs, 5,892 pages, 479,447,993 bytes, and zero
  acquisition quarantines;
- both masonry versions match the exact hashes, sizes, page counts, order, and evidenced
  version relationship above;
- Volume 17 reports distinct requested/resolved URL, remote filename, and safe local path;
- changing the catalog succeeds consistently only when that same catalog is supplied to every
  command;
- a second acquisition reuses all identical artifacts without rewriting them;
- `publish-check` remains non-zero only for deferred review flags, proving acquisition success
  cannot bypass semantic publication safety.

If a live official endpoint has genuinely drifted, the run still completes and records the
exact terminal mismatch. The task is not marked done until the drift is reconciled through an
explicit curated catalog change backed by the fetched official evidence.

## Evidence

`make verify` passed on 2026-09-03 with pnpm activated through a temporary Corepack shim.
Ruff and its format check passed over 176 files, strict mypy passed over 151 source files, all
seven import contracts were kept, pytest reported `225 passed`, and frontend lint, typecheck,
and production build passed. The focused acquisition suite contains 31 passing tests. Its
regressions now cover immutable first-network evidence, legacy receipt migration, explicit
historical CAS indexing, rejected unindexed CAS objects, all five owned interrupted-write temp
families, unknown and unsafe temp blockers, and valid preexisting targets whose mandatory
network re-attestation fails.

Real acquisition root: `/tmp/cadgpt-inbr-acquisition.GzxDl0`

```text
$ uv run cadgpt-regulations acquire \
    --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json \
    --output-root /tmp/cadgpt-inbr-acquisition.GzxDl0
wrote deterministic acquisition receipt: /tmp/cadgpt-inbr-acquisition.GzxDl0/acquisition.json
metadata 9/9 ready; PDFs 43/43 ready
acquired 43; reused 0; pages 5892; bytes 479447993; quarantined 0

$ uv run cadgpt-regulations acquisition-check \
    /tmp/cadgpt-inbr-acquisition.GzxDl0/acquisition.json \
    --root /tmp/cadgpt-inbr-acquisition.GzxDl0 \
    --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json
valid acquisition: 9/9 metadata, 43/43 PDFs, 5892 pages, 479447993 bytes

$ uv run cadgpt-regulations inventory \
    /tmp/cadgpt-inbr-acquisition.GzxDl0/artifacts \
    --output /tmp/cadgpt-inbr-acquisition.GzxDl0/manifest.json \
    --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json
wrote deterministic manifest: /tmp/cadgpt-inbr-acquisition.GzxDl0/manifest.json
accounted 43/43 expected artifacts across 43 files
valid PDFs 43; PDF pages 5892; quarantined 0; missing 0; unaccounted 0

$ uv run cadgpt-regulations validate \
    /tmp/cadgpt-inbr-acquisition.GzxDl0/manifest.json \
    --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json
valid manifest: 43 files, 43 valid PDFs, 5892 PDF pages, 0 quarantined

$ uv run cadgpt-regulations publish-check \
    /tmp/cadgpt-inbr-acquisition.GzxDl0/manifest.json \
    --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json
not publishable: 3 blocker(s)
- guide-masonry-perimeter-walls-v3-1404.pdf: NEEDS_REVIEW: GUIDE_FOR_VOLUME_08_UNVERIFIED
- guide-masonry-perimeter-walls-v2-1403.pdf: NEEDS_REVIEW: GUIDE_FOR_VOLUME_08_UNVERIFIED
- دستور-کار-ارزیابی-ایمنی-و-بهسازی_photo.pdf: NEEDS_REVIEW: PUBLICATION_METADATA_UNRESOLVED
exit 1

$ uv run cadgpt-regulations acquire \
    --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json \
    --output-root /tmp/cadgpt-inbr-acquisition.GzxDl0
wrote deterministic acquisition receipt: /tmp/cadgpt-inbr-acquisition.GzxDl0/acquisition.json
metadata 9/9 ready; PDFs 43/43 ready
acquired 0; reused 43; pages 5892; bytes 479447993; quarantined 0

$ uv run cadgpt-regulations acquisition-check \
    /tmp/cadgpt-inbr-acquisition.GzxDl0/acquisition.json \
    --root /tmp/cadgpt-inbr-acquisition.GzxDl0 \
    --catalog packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json
valid acquisition: 9/9 metadata, 43/43 PDFs, 5892 pages, 479447993 bytes
```

All nine official WordPress records have unique raw, projection, and semantic hashes. Their
raw and projection files are content-addressed, and the stored projections match the curated
ordered link sets. The catalog SHA-256 is
`2d3e73e6c812252a07ef35cb10fd6059cf0c311af23daff92ff67d371e7cef0c`, and the manifest
SHA-256 remains `c762c8cd9663fc70be2103697025ab3dc25a818ac85710511f4500c6dcf204ab`.

The two masonry records are catalog orders 39 and 40. Version 3 / 1404 is 68 pages,
3,845,085 bytes, SHA-256
`acd530ac4b887bdf4924aa614d901becf9d06c95717f6a1934005ff9316447a3`; version 2 / 1403
is 75 pages, 5,217,505 bytes, SHA-256
`f1eb68785aa4abb57b537f06c850ec67b8344355ef0fce4f12aadb194f8f773c`. Version 3 has the
evidenced `SUPERSEDES` relationship to version 2. Both provisional `GUIDE_FOR volume-08`
relationships remain `needs_review` and therefore fail publication.

Volume 17's immutable `initial_transport` records its requested and resolved URL as
`https://inbr.s3.ir-thr-at1.arvanstorage.ir/mabahse%2Fmabahse17%2Fmabhas17-watermark-1403-02.pdf`,
the inert remote filename as `mabahse/mabahse17/mabhas17-watermark-1403-02.pdf`, and the flat
local path as `mabahse_mabahse17_mabhas17-watermark-1403-02.pdf`. Its acquired PDF is 259
pages and 30,183,839 bytes with SHA-256
`eb575703d82dfe524ea227c1115c487f0d8c65aebb96442859ff68795fa70cc8`.

The pre-migration legacy reused receipt had SHA-256
`6e078ed850268742fa4cc88322f05e31410bb0d81049aac036d2ca44cd0551f0`. The unattended
v2 migration deliberately re-fetched all 43 PDFs because that legacy receipt had no retained
network attestation; its acquired receipt SHA-256 was
`bcf0722b711e18b3432d0ab731efcb8c2a1fbc19f00868aabecfe9ff5be24416`. The following v2
reuse receipt has SHA-256
`a7b35fb75982bdf17daccf526b83db810369b50cbc537ba1bed34965015515df`.

Both v2 receipts contain 43 non-null `initial_transport` records. Their ordered
`catalog_key`/attestation digest is identically
`3386348e9224d68db970cf68ebeac37f09fb436458b3e5d0137abb9a90112ef6`, proving reuse did
not replace the first successful network evidence. The live history index is empty because
this successful corpus had neither retained quarantines nor interrupted writes; the focused
tests prove failed-then-successful retention and temp recovery are explicitly indexed.

Before migration, after the acquired v2 pass, and after the reuse pass, the ordered artifact
content digest was identically
`a77ea1431647213ffb0a1315d2562b4a4bf174532ba799fc06414b78a570f301`, and the ordered
filename/mtime/size digest was identically
`8fd4a11e7af0b3e4d65601fdd3d32e2e4a936cc9c1769607e8473e88fc9b4c14`. All 43 reused
results have zero attempts, null status/resolved URL, and an empty current redirect chain.
Thus neither migration nor reuse rewrote an artifact. `docs/inbr/` has no diff, and no
downloaded evidence is tracked in the repository.

Wiring: `cadgpt-regulations acquire` enforces the fixed official HTTPS INBR origin set,
manual bounded redirects, per-operation and monotonic total timeouts, streamed hashing,
content-addressed quarantine, and no-clobber installation. `acquisition-check` binds the
receipt to the catalog and on-disk canonical receipt, re-attests all stored bytes and managed
directories, rehashes every explicitly indexed history entry, and rejects correctly named but
unindexed CAS objects as well as missing, extra, symlinked, or non-regular entries. Startup
recovers only owned, recognized interrupted-write patterns into content-addressed terminal
history; unknown or unsafe temporary entries remain blockers. The output root must be
caller-created, current-user-owned, and not group/world writable. A same-user process can
still race pathname-based directory operations; directory re-attestation mitigates this, and
the remaining local race is documented in `docs/decisions.md` for later `openat`/dirfd
hardening if the threat model expands.

## Review

The review identified three fix-now findings. This remediation preserves the first successful
artifact transport attestation across reuse, replaces blanket CAS admission with a strict
current-plus-history index, and recovers only recognized interrupted writes into terminal
history. The focused regressions, full verification run, and two-pass live migration above
cover all three findings. No additional review was requested; the separately queued follow-up
items remain outside T-0025's fix-now scope.
