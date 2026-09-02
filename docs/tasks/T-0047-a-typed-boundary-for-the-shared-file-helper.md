# T-0047 — `base/files.py` is untyped at a module boundary

**Phase:** 3   **Status:** open
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

## Review
