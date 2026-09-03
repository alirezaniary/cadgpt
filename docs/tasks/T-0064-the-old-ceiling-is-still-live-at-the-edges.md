# T-0064 — The number T-0033 deleted is still live at the edges

**Phase:** 3   **Status:** open
**Touches invariants:** none.

## Why

Found by the T-0033 review. T-0033 replaced a 512MB ceiling nobody derived with a measured one, but
the old number is still enforced and still documented at two edges the derivation did not reach:

- `deploy/docker/nginx.conf:18` is still `client_max_body_size 512m`;
- `media/constants.py:22` still reads *"so a 500MB model never sits in memory"*.

The effect appears only through the real web path, not the direct-to-gunicorn `curl` the evidence
used — which is why the evidence did not catch it. A user picking a 400MB file **transfers all
400MB** (`proxy_request_buffering off`, so it streams through to gunicorn and lands in a temp file)
before being told the limit is 100MB. On an office upload link that is minutes of waiting for a
refusal that was knowable from the file picker.

There is also no client-side size guard: the ceiling is stated as text beside the input and nothing
checks the chosen file before the upload starts.

## Scope

**Changes**

- The edge rejects what the application rejects, rather than accepting five times more and
  discarding it after transfer. `client_max_body_size` follows the derived ceiling.
- The browser refuses an over-size file before uploading it. The file input knows the size at
  selection; nothing needs to be transferred to find out.
- The stale comment in `media/constants.py` says what is now true.

**What explicitly does not change**

- The derived ceiling itself, or `MAX_BYTES[IDS_RULESET]`.
- Chunked or resumable upload, still deliberately not built.

## How to prove it ran

`make verify`, then through the **real web path** — the nginx-served frontend, not curl straight to
gunicorn: an over-size file refused without transferring the whole body, shown by the response and by
the absence of a temp file. Then the same file refused in the browser before any request is made,
rendered.

## Evidence

## Review
