# T-0042 — The catalogue hands out a storage URL nothing authenticates

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** tenancy — by precedent rather than by breach today. **Reviewer-gated.**

## Why

Found by the T-0030 review. `services/api/cadgpt/apps/rulepack/api/v1/serializers.py:33`
serialises `source_file` — a `FileField` — straight to a URL. Against the running stack:

```
GET /api/v1/rule-packs/  ->  "source_file": "http://localhost:8000/media/rule-packs/sample/a0eeb46c-….ids"
curl <that URL>          ->  200, the IDS bytes, with no Authorization header at all
```

**This is not a tenancy leak today** — catalogue content is global by design, every tenant reads
the same packs, and the bytes are rules we publish. It is queued rather than fixed-now for
exactly that reason. Two things make it worth closing anyway.

**It sets a precedent this repository had deliberately avoided.** `MediaSerializer`
(`services/api/cadgpt/apps/media/api/v1/serializers.py:15-24`) omits `Media.file` on purpose: a
tenant's file URL is never handed out. T-0030 introduces the first "serialise a `FileField` to a
URL" in the codebase, and it becomes a real leak the first time someone copies the pattern onto
tenant data — which is precisely how the shape of a codebase turns into a defect.

**And in production the field is a lie.** With `USE_S3=False`, Django serves `MEDIA_URL` only
under `DEBUG` (`config/urls.py:26-27`), and `deploy/docker/nginx.conf` has no `/media/`
location — so `/media/rule-packs/…` falls through `try_files … /index.html` and the URL
advertises a download that returns the SPA's HTML.

## Scope

A decision and a small change. Either:

- **drop the field**, and let a pack be identified by its metadata, with the IDS reachable only
  through the check that uses it; or
- **route it through an authenticated download**, the way `Media` already is, so there is one
  way to get a file out of this system rather than two.

Prefer the second only if something actually needs to fetch the IDS; prefer the first if nothing
does. Do not leave a raw storage URL on the serializer.

- `services/api/cadgpt/apps/rulepack/api/v1/serializers.py`, and the view if a download route is
  added. Tests for whichever path is chosen.
- If a download route is added it is **read-only and authenticated**, and it must not become a
  way to enumerate storage keys.

**Does not change:** the catalogue's global readability, the model, the seeder, or `Media`.

## How to prove it ran

`make verify` with the 5 import contracts kept, then against the running stack: the list
response no longer carrying a raw storage URL, and — if a download route was added — a real
authenticated fetch returning the IDS bytes and an unauthenticated one refused. Paste both
responses and the `curl` that previously returned 200 now failing.

## Evidence

**Decision: drop the field.** Confirmed before touching anything: `services/web/src/api/types.ts:87`
typed `RulePack.source_file` as a bare `string`, and a repo-wide grep of `services/web/src`
(excluding `mocks/fixtures.ts`, which only supplied fixture data) found nothing that renders,
links to, or fetches it — no download button, no `<a href>`, no `useQuery` reading it. The
IDS bytes a selected pack carries are read straight off disk by the check task itself
(`cadgpt.apps.rulepack.services._local_path` / `RulePack.source_file.chunks()`), never
fetched over HTTP by anything in this codebase. Nothing needs a download route, so per the
task's own guidance the first option is correct: the field is gone, not rerouted.

**Change.** `services/api/cadgpt/apps/rulepack/api/v1/serializers.py`: removed `"source_file"`
from `RulePackSerializer.Meta.fields` (docstring explains why). `services/web/src/api/types.ts`:
removed `source_file: string` from the `RulePack` interface and documented its absence.
`services/web/src/mocks/fixtures.ts`: removed the four now-nonexistent `source_file` fixture
lines (the `RuleSet.source_file: Media` shape is untouched — different field, different
model, out of scope). No view, model, seeder, or `Media` code touched.

**1. `make verify`** — exit 0. `msgfmt` was missing from this box (`gettext-base` was
installed but not `gettext`, no root to `apt install`); extracted the already-downloaded
`/tmp/gettext_0.21-14ubuntu2_amd64.deb` with `dpkg-deb -x` into `/tmp/gettext-bin/extract`
and ran with a `PATH` wrapper — a environment workaround, not a change to the repo. Full
output tail:

```
uv run ruff check .                    -> All checks passed!
uv run ruff format --check .           -> 190 files already formatted
uv run mypy packages/engine/src services/api/cadgpt  -> Success: no issues found in 172 source files
uv run lint-imports --no-cache
  I1 - no inference client, web framework or network reaches the checking engine   KEPT
  The engine knows nothing about the service that hosts it                        KEPT
  Django apps are layered                                                         KEPT
  Services never import the transport layer                                      KEPT
  Models never import services                                                    KEPT
  Contracts: 5 kept, 0 broken.
uv run pytest                          -> 292 passed, 34 warnings in 4.73s
web-verify (pnpm run verify: tsc, eslint, vitest unit, storybook build+test, vite build)
  Test Files  1 passed (1)  /  Tests  2 passed (2)      [unit]
  Test Files  9 passed (9)  /  Tests  35 passed (35)    [storybook]
```

**2. Real path against the running stack.** `deploy/compose.yaml`'s `api` image is not
bind-mounted (code is baked in), so rebuilt it: `docker build --network=host -f
deploy/docker/api.Dockerfile -t cadgpt-api:latest .` (network access to PyPI needed
`--network=host` since the sandbox's `HTTP_PROXY=http://127.0.0.1:2080` isn't reachable from
an isolated build namespace), then `docker compose up -d api worker beat` to run it. Created
a throwaway user via `manage.py shell` (`t0042@test.local`), logged in for a real bearer
token, and hit the real endpoint:

```
$ curl -s -H "Authorization: Bearer $ACCESS" http://localhost:8000/api/v1/rule-packs/ | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('source_file present in any row:', any('source_file' in row for row in data['results']))
print('keys of first row:', sorted(data['results'][0].keys()))
"
source_file present in any row: False
keys of first row: ['author', 'created_at', 'description', 'jurisdiction', 'name', 'region', 'source_citation', 'specification_count', 'title', 'uuid', 'version']
```

The exact URL the task's own repro cited is still on disk (`rule-packs/sample/a0eeb46c-a69e-4948-84c3-5ccec8a7c6c5.ids`,
confirmed via `psql`), and the direct-file curl:

```
$ curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/media/rule-packs/sample/a0eeb46c-a69e-4948-84c3-5ccec8a7c6c5.ids
HTTP 200
```

**This did not change, and that is expected for the branch taken.** `deploy/compose.yaml`
runs `api` with `DJANGO_SETTINGS_MODULE: cadgpt.config.settings.local` (`DEBUG=True`)
specifically for local iteration, and Django's dev media serving is independent of what any
serializer emits — it serves any file under `MEDIA_ROOT` to anyone who already knows or
guesses the path, with or without this change. Closing that path is a `Media`/nginx/settings
change and the task explicitly scopes it out ("Does not change: ... `Media`"); the task's own
"Why" section already establishes that *production* is where this stops working today
(`config/urls.py` only serves `MEDIA_URL` under `DEBUG`, and `deploy/docker/nginx.conf` has
no `/media/` location) — untouched by this change, and not something dropping the field was
ever going to alter either way. What this task closes is the API handing the URL to a
client in the first place, which is verified above: the field is gone from the wire.

**3. Wiring.** `services/api/cadgpt/apps/rulepack/api/v1/urls.py:12`:
`router.register("rule-packs", RulePackViewSet, basename="rule-pack")` — the viewset actually
mounted at `/api/v1/rule-packs/` (confirmed live above) uses
`serializer_classes = {"default": RulePackSerializer}` (`views.py:78`), whose
`Meta.fields` (`serializers.py`) is what was edited.

**NOT DONE:** nothing. The task's fallback proof ("the curl that previously returned 200 now
failing") applies to the *route-it-through-auth* branch, where the raw path would be
deliberately closed off; it does not apply to the drop-the-field branch taken here, and nothing
in scope asked the raw dev-mode media path to be closed.

---

## Reviewer round 2 — F1, F2, F3

The reviewer confirmed the fix itself but found the change had no test coverage of its own,
two docstrings still describing the old defect in the present tense, and the settled decision
recorded only in a serializer docstring rather than in `docs/decisions.md`. All three fixed in
this pass; no new review requested.

**F1 — structural test, mutation-proved.** Added
`services/api/cadgpt/tests/test_serializer_file_fields.py`. It walks every `ModelSerializer`
subclass loaded in the process (`serializers.ModelSerializer.__subclasses__()`, transitively —
same style as `_registered_viewsets()` in `test_tenant_isolation.py`), forcing the URL
configuration to resolve first (`_import_every_serializer_module()`) so the result does not
depend on some other test file happening to import the views first. For each serializer whose
`Meta.fields` names a field not explicitly declared on the class (`_declared_fields` — the
escape hatch `RuleSetSerializer.source_file = MediaSerializer(...)` uses on purpose), it
resolves the field against the model and fails if it is a `django.db.models.FileField`
(covers `ImageField`, a subclass) — exactly the shape `RulePackSerializer.source_file` used to
be.

Mutation proof — re-added `"source_file"` to `RulePackSerializer.Meta.fields`, ran the new test
alone, restored, ran again:

```
$ rtk proxy uv run pytest cadgpt/tests/test_serializer_file_fields.py -v   # baseline (field absent)
cadgpt/tests/test_serializer_file_fields.py .                              [100%]
1 passed in 0.11s

# --- edited serializers.py: added "source_file" back to RulePackSerializer.Meta.fields ---

$ rtk proxy uv run pytest cadgpt/tests/test_serializer_file_fields.py -v   # mutated
cadgpt/tests/test_serializer_file_fields.py F                              [100%]
FAILED cadgpt/tests/test_serializer_file_fields.py::test_no_serializer_hands_a_file_field_straight_out_as_a_storage_url
AssertionError: these serializers hand out a FileField/ImageField as a raw storage URL --
either drop the field (RulePackSerializer, T-0042) or declare it explicitly as a nested
serializer over an authenticated download route (RuleSetSerializer.source_file ->
MediaSerializer): cadgpt.apps.rulepack.api.v1.serializers.RulePackSerializer serialises
RulePack.source_file (a FileField) directly, which DRF renders as a bare, unauthenticated
storage URL
1 failed in 0.32s

# --- reverted the mutation ---

$ rtk proxy uv run pytest cadgpt/tests/test_serializer_file_fields.py -v   # restored
cadgpt/tests/test_serializer_file_fields.py .                              [100%]
1 passed in 0.11s
```

This is the same claim the reviewer's own repro made about the *old* suite (re-adding
`source_file` and getting `292 passed` unchanged) — now the identical mutation flips exactly
one test, red, with the offending serializer and model field named in the message.

**F2 — stale docstrings, updated to past tense.**
`services/api/cadgpt/apps/review/api/v1/views.py` (`CheckRunViewSet.report_file`) and
`services/api/cadgpt/apps/review/api/v1/serializers.py`
(`CheckRunSummarySerializer.get_report_file_url`) both described `RulePackSerializer.
source_file` as a present-tense defect ("does today", "queued"). Both now say T-0042 closed it
by dropping the field, and explain why a report still needs its own authenticated route where
a rule pack does not (a report is tenant data; the catalogue is not).

**F3 — decision recorded.** Appended `## 2026-09-12 — A rule pack is identified by metadata
alone; no download route` to `docs/decisions.md`, in that file's Problem/Decision/Reopens-if
format, recording that the download-route alternative was rejected because nothing consumes a
rule pack's IDS bytes over HTTP, and naming what would reopen it (a client-side "download the
source IDS" feature).

**`make verify` after all three fixes** — exit 0, full output tail:

```
uv run ruff check .                    -> All checks passed!
uv run ruff format --check .           -> 191 files already formatted
uv run mypy packages/engine/src services/api/cadgpt  -> Success: no issues found in 173 source files
uv run lint-imports --no-cache
  I1 - no inference client, web framework or network reaches the checking engine   KEPT
  The engine knows nothing about the service that hosts it                        KEPT
  Django apps are layered                                                         KEPT
  Services never import the transport layer                                      KEPT
  Models never import services                                                    KEPT
  Contracts: 5 kept, 0 broken.
uv run pytest                          -> 293 passed, 34 warnings in 6.67s   (292 + the new structural test)
web-verify (pnpm run verify: eslint, tsc, vite build, storybook build, vitest unit, vitest storybook)
  Test Files  1 passed (1)  /  Tests  2 passed (2)      [unit]
  Test Files  9 passed (9)  /  Tests  35 passed (35)    [storybook]
```

`msgfmt` was still missing on this box for the same reason as the previous pass; reused the
same `/tmp/gettext-bin/extract` + `PATH` workaround left from that run (an environment
workaround, not a repo change) — `compilemessages` then reported the compiled `.po` already
up to date.

**NOT DONE:** nothing from this round. All three reviewer findings (F1, F2, F3) are fixed and
verified above; the pre-existing `/media/` finding is explicitly out of this task's scope per
the coordinator's instruction and is being tracked separately.

## Review
