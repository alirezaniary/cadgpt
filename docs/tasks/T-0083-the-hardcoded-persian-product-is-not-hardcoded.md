# T-0083 — The hardcoded-Persian product never activates Persian on the server

**Phase:** 3   **Status:** open
**Touches invariants:** none directly. Adjacent to "every user-facing string goes through
gettext" (`CLAUDE.md`) — the strings do; the language they render in is accidental.

## Why

Found while proving T-0056's real-path evidence. The frontend was settled in T-0072 as
"single-language, hardcoded to Persian, not user-switchable" — every frontend string is a
fixed Persian literal regardless of the visiting browser. The server side of the same product
was never given the equivalent decision:

- `LANGUAGE_CODE = "en"` in `services/api/cadgpt/config/settings/base.py:124`.
- `LocaleMiddleware` is active, so whichever language it activates for a request is whatever
  `Accept-Language` header arrived with it.
- `services/web` never sends an `Accept-Language` header on any request (grepped across
  `services/web/src`; the only hit is an unrelated comment in
  `report_generation.py`).

So every `gettext`-wrapped string the server writes into a stored, user-facing field —
`CheckRun.failure_detail` (T-0056, T-0048), report prose (T-0026, T-0029), validation and
conflict messages throughout `services/*/services/*.py` — renders in whatever language the
visiting browser's own locale happens to request, which for almost every real deployment
means English, in a product whose entire frontend is fixed Persian. Verified directly: an
unforced browser session showed T-0056's new failure text and long-shipped T-0026/T-0029
report prose both in English in the same page; the identical server call with an explicit
`Accept-Language: fa` header produced correct Persian for the parts triggered synchronously
inside that request.

There is a second, harder layer underneath the missing header. Most of the affected text —
report bodies, most `CheckRun.failure_detail` values — is written by the **Celery worker**,
which never has an HTTP request or an `Accept-Language` header at all. A frontend header fix
only reaches the synchronous half (like T-0056's `_reap_lost_dispatch`, which runs inside the
request). The worker half needs its own answer to "which language," independent of any
request — most plausibly a hardcoded `fa` activation at the top of `execute_check_run`,
matching the product decision, rather than a per-tenant or per-request language that does not
exist yet.

## Scope

**Changes**

- Decide and implement how the server settles on Persian without depending on the caller:
  most directly, activate `fa` explicitly wherever server-generated user-facing text is
  produced — the Celery worker's task entrypoint, and (if kept as a defense in depth)
  `LocaleMiddleware`'s default. Changing `LANGUAGE_CODE` to `"fa"` alone does not reach the
  worker, which has no request and thus no middleware.
- Confirm nothing currently relies on `Accept-Language`-driven English for a legitimate
  reason (e.g. an admin tool, a management command) before removing the dependency.
- A regression test that does not merely assert a translated string exists (that already
  passes today under the wrong assumption) but that the *stored* value is Persian when
  produced with no `Accept-Language` header at all — the shape of every real worker call.

**What explicitly does not change**

- The frontend's own strings, already fixed Persian since T-0072.
- T-0056's `_reap_lost_dispatch` mechanism itself — this task is about the language it writes
  in, not the recovery logic.

## How to prove it ran

`make verify`, then against `make up`: trigger a worker-produced failure (or reuse T-0056's
`dispatch_lost` path) with **no** `Accept-Language` header sent anywhere in the request chain,
and show the stored `failure_detail` (or report prose) is Persian. Then show the existing
English-language paths this task removes reliance on — if any caller legitimately wants
English, name it and say what happens to it now.
