# T-0047 — `base/files.py` is untyped at a module boundary

**Phase:** 3   **Status:** done
**Touches invariants:** types at module boundaries.

## Why

Found by the T-0031 review. `services/api/cadgpt/apps/base/files.py` was extracted during T-0031
so `RulePackService` and `MediaService` share one `local_path` rather than keeping two copies of
the same storage fallback. The extraction is right and the review confirmed it is
behaviour-preserving — the copy chunk size is the same value it was, and `_readable_path` is
logic-identical to the `MediaService` method it replaced.

What is wrong is the signature: `local_path(file_field: Any, display_name: str)` and
`_readable_path(file_field: Any)`. `mypy --strict` passes over this module only because `Any`
switches the checking off — every `.open()`, `.close()`, `.path` and the `copyfileobj` iteration
is unchecked. `CLAUDE.md` requires types at module boundaries, and this is a new module boundary
shared by two apps.

Both call sites pass a `django.db.models.fields.files.FieldFile`.

## Scope

**Changes**

- `base/files.py` typed against what it actually receives, so `mypy --strict` is checking the
  attribute access rather than being told not to. `FieldFile` is the concrete type; a `Protocol`
  naming only the members used is the alternative and is the better answer if it keeps the module
  independent of Django's storage internals. Pick one, say which in the evidence, and say why.

**What explicitly does not change**

- The behaviour, the chunk size, the fallback logic, or either call site's semantics. This is a
  typing change; if it alters what the function does, it has gone wrong.

## How to prove it ran

`make verify` with `mypy --strict` green and the 5 contracts kept, plus: a deliberately wrong
call (passing something without `.path`) now rejected by `mypy` where it was previously accepted.
Paste the error. That is the whole point of the task — a type that catches nothing is not a fix.

## Evidence

**Choice: `FieldFile`, not a `Protocol`.** Both call sites already pass a
`django.db.models.fields.files.FieldFile` (`rule_pack.source_file`, `media.file`), the module's
own docstring already talks in Django storage terms ("Django's in-memory storage", "an S3
backend"), and `services/api` already depends on `django-stubs` with the mypy Django plugin
wired in (`pyproject.toml`: `plugins = ["mypy_django_plugin.main", "mypy_drf_plugin.main"]`,
`[tool.django-stubs] django_settings_module = "cadgpt.config.settings.test"`). That stub already
gives a fully-typed `FieldFile` (`.path -> str`, `.open(mode: str = "rb") -> Self`,
`.close() -> None`, and `.read`/iteration via `File[Any](FileProxyMixin[AnyStr], IO[AnyStr])`).
Per CLAUDE.md's "inherit before writing," writing a hand-rolled `Protocol` here would duplicate
type surface that `django-stubs` already maintains and would drift from it (e.g. `open`'s
`Self` return, or the exception-raising `.path` property) for no independence this module
doesn't already forgo — `cadgpt.apps.base` is a Django app, not the engine package the import
contracts keep framework-free. A `Protocol` would be the right call if this module needed to
stay ignorant of Django (as `packages/engine` must); it does not, so `FieldFile` is the direct,
inherited type.

**`make verify`:** exit 0, full run below.
```
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 173 source files
uv run lint-imports --no-cache
Contracts: 5 kept, 0 broken.
uv run pytest
296 passed, 34 warnings in 6.51s
web-verify: pnpm run verify -> vitest unit: 2 passed (1 file); storybook: 35 passed (9 files); vite build succeeded
```

**Real path:** the review-check pipeline is the real caller of this function end to end
(`ReviewExecutionService` -> `MediaService.local_path` / `RulePackService.local_path` ->
`cadgpt.apps.base.files.local_path`), and it runs against real IFC/IDS fixture files, not mocks.
Reran it directly (unfiltered, via `rtk proxy` since the rtk hook's own pytest summariser
mis-reports "No tests collected" for this invocation even though real collection happens):

```
$ rtk proxy uv run pytest services/api/cadgpt/apps/review/tests/test_check_run.py -v
collected 21 items
services/api/cadgpt/apps/review/tests/test_check_run.py ..................... [100%]
...
PytestUnraisableExceptionWarning: Exception ignored in: <function file.__del__ at 0x70ae0fcf82c0>
  File ".../ifcopenshell/file.py", line 649, in __del__
    del file_dict[self.file_pointer()]
KeyError: 135724432
======================== 21 passed, 9 warnings in 3.77s ========================
```
The `ifcopenshell/file.py` warning on teardown is the tell that a real IFC file was actually
opened and parsed through the path this function materialized — not a stub.

**The type actually catches something.** Before this change the parameter was `Any`, so a
value with no `.path` at all passed silently:
```
$ git stash   # revert to the Any-typed version
$ uv run mypy services/api/cadgpt/apps/base/files.py /tmp/t0047/bad_call.py
Success: no issues found in 2 source files
$ git stash pop
```
where `/tmp/t0047/bad_call.py` was:
```python
from cadgpt.apps.base.files import local_path


class NotAFieldFile:
    """Something that quacks like a file but has no `.path`."""

    def read(self, size: int = -1) -> bytes:
        return b""


def use_it() -> None:
    with local_path(NotAFieldFile(), "model.ifc") as path:
        print(path)
```
After the change, the identical call is rejected:
```
$ uv run mypy services/api/cadgpt/apps/base/files.py /tmp/t0047/bad_call.py
/tmp/t0047/bad_call.py:12: error: Argument 1 to "local_path" has incompatible type "NotAFieldFile"; expected "FieldFile"  [arg-type]
Found 1 error in 1 file (checked 2 source files)
```

**Wiring** — both real call sites are unchanged and now type-checked against the concrete
signature rather than `Any`:
- `services/api/cadgpt/apps/rulepack/services.py:185`:
  `with _local_path(rule_pack.source_file, rule_pack.name) as path:`
- `services/api/cadgpt/apps/media/services.py:62`:
  `with _local_path(media.file, media.original_name) as path:`

**NOT DONE:** nothing. Scope was typing-only and is complete; behaviour, chunk size and
fallback logic are untouched (see diff: 4 insertions / 3 deletions, all in signatures and the
one new import).
