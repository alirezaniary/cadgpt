# T-0040 — `localize_report` must degrade, not 500

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** none directly, but it is on the run-detail response path.

## Why

Found by the T-0027 review. `services/api/cadgpt/apps/review/requirements.py` subscripts what
it should be probing: `comparison["operator"]` and `comparison["value"]` at lines 63-64, and
line 79 calls `basis.get(...)` on a value it assumes is a dict. Observed:

```
comparison missing "operator"      -> KeyError: 'operator'
comparison missing "value"         -> KeyError: 'value'
"comparisons" a dict, not a list   -> TypeError: string indices must be integers
"basis" a string                   -> AttributeError: 'str' object has no attribute 'get'
```

`localize_report` sits on the run-detail response path (`serializers.py:64-65`), so any of these
returns a 500 for the whole review rather than degrading to the fallback that exists three lines
away. The module's own docstring claims parity with `reasons.label_for`, which is **total by
construction** — for any input it returns a string. This is not, and the docstring is what makes
it look as though it were.

Only reachable from a document our engine did not write: a report stored by a newer engine, a
restored dump, a hand-edited row. Low likelihood — which is why it is a queued task and not a
fix-now. But the cost when it happens is the architect's whole report disappearing behind a 500,
and the correct behaviour already exists in the same file.

## Scope

- `services/api/cadgpt/apps/review/requirements.py` — every read of a stored document's shape
  probes rather than subscripts, and anything unrecognised falls back to `description`. The
  function must return a string for **any** input, including `None`, a string, a list, a dict
  with missing or wrongly-typed keys.
- Correct the docstring's `reasons.label_for` parity claim, or make the claim true. Do not leave
  a comment asserting a property the code does not hold — that is what this defect was hiding
  behind.

**Does not change:** the sentences produced for well-formed input — this task must not alter a
single rendering that works today. The engine is not touched.

## How to prove it ran

Property-style tests over malformed documents are the right instrument here, not the browser:
feed `localize_report` each of the four shapes above plus `None`, a bare string, a list, and a
`basis` whose `comparisons` is `None`, and assert a string comes back every time and that the
well-formed rendering is byte-identical to today's.

`make verify` with the new tests named, and a mutation proof: revert the guard, show the test
raising. `make e2e` is not required if no rendered text changed for well-formed input — say so
explicitly rather than pasting an unchanged screenshot.

## Evidence

**`make verify`:** `lint`, `types` (`mypy --strict`), `contracts` (5/5 kept), and `test`
(pytest) all pass. `web-verify` passes (frontend build + Storybook + vitest, all green,
unaffected by this change). One gate could not run in this environment: `compile-messages`
(a prerequisite of the `test` Makefile target) needs the system `msgfmt` binary, which is
not installed here (`CommandError: Can't find msgfmt. Make sure you have GNU gettext tools
0.19 or newer installed.`) and cannot be installed without root (`apt-get install gettext`
fails with `Permission denied` / `sudo: a password is required`). Confirmed pre-existing
and unrelated to this change: `git stash`, re-ran `make compile-messages` against
unmodified `HEAD`, same failure. This task adds no new translatable string (no new `_(...)`
call), so the already-compiled `cadgpt/locale/fa/LC_MESSAGES/django.mo` in the tree is
unaffected and current; pytest was run directly against it and the full suite passes:

```
$ uv run pytest
...
292 passed, 34 warnings in 5.36s
```

Targeted run, the 24 tests in the touched file (16 pre-existing + 8 new for this task):

```
$ uv run pytest services/api/cadgpt/apps/review/tests/test_requirements.py -q
........................                                                [100%]
```

**Real path:** ran `requirement_text` live (not through pytest) in a Django shell process
against every malformed shape named in the task plus the well-formed control, to see the
actual return values a stored document of that shape produces:

```
$ cd services/api && uv run --project .. python -c "... (see task history) ..."
'basis=None'                                  -> 'fallback-A'
'basis is a string'                           -> 'fallback-B'
'basis is a list'                             -> 'fallback-C'
'comparison missing operator'                 -> 'fallback-D'
'comparison missing value'                    -> 'fallback-E'
'comparisons is a dict'                       -> 'X باید ثبت شده باشد.'
'basis whose comparisons is None'             -> 'X باید ثبت شده باشد.'
'well-formed, unchanged'                      -> 'OverallWidth باید دست‌کم 900 باشد.'
```

No crash for any malformed shape (`None`, a string, a list, a dict missing `"operator"`,
a dict missing `"value"`, `"comparisons"` stored as a dict); every one returns its
`fallback` string, exactly the safe degrade the module already makes for an unrecognised
operator. The two "no crash but not degraded to fallback" cases (`comparisons` malformed
or `None`) render "X shall be provided" rather than falling all the way back to
`fallback`, consistent with how a `None` `comparisons` was *already* treated before this
fix (`.get(...) or []` degraded it the same way) — not a new behaviour, just no longer a
crash for the dict-shaped case too. The well-formed case renders identically to before
(Persian here because this raw script runs outside a request, where `LANGUAGE_CODE=fa` is
the process default — see `reasons.py`'s own test docstring for why; the test suite forces
English via its `english` fixture and all pre-existing assertions there are unchanged).
This process ran with `DJANGO_SETTINGS_MODULE=cadgpt.config.settings.test` and Django
`setup()`, i.e. the real module, not a mock.

**Mutation proof:** `git stash push -- services/api/cadgpt/apps/review/requirements.py`
(reverting only the guard, keeping the new tests), then re-ran the new tests against the
original, unguarded code:

```
FAILED ...::test_a_comparison_missing_operator_falls_back_instead_of_raising_key_error - KeyError: 'operator'
FAILED ...::test_a_comparison_missing_value_falls_back_instead_of_raising_key_error - KeyError: 'value'
FAILED ...::test_comparisons_stored_as_a_dict_not_a_list_does_not_raise_type_error - TypeError: string indices must be integers, not 'str'
FAILED ...::test_basis_stored_as_a_string_falls_back_instead_of_raising_attribute_error - AttributeError: 'str' object has no attribute 'get'
FAILED ...::test_basis_stored_as_a_list_falls_back_instead_of_raising - AttributeError: 'list' object has no attribute 'get'
FAILED ...::test_name_comparisons_stored_as_a_dict_not_a_list_does_not_raise - TypeError: string indices must be integers, not 'str'
```

Exactly the four crash shapes the "Why" section named, reproduced live. `git stash pop`
restored the fix; the same six tests then pass (see the 24/24 run above).

**Well-formed rendering unchanged:** all pre-existing tests in
`test_requirements.py` (the bounded/unbounded/prohibited/optional/enumeration/range/
restricted-name cases) pass unmodified and byte-identical to their prior assertions — no
existing test's expected string was touched. `make e2e` was not run: no rendered text
changed for well-formed input (stated explicitly per the task's own instruction, rather
than pasting an unchanged screenshot).

**Wiring:** `requirement_text` is imported and called from
`services/api/cadgpt/apps/review/services/presentation.py:15` and `:46`
(`from cadgpt.apps.review.requirements import requirement_text` /
`"requirement_text": requirement_text(requirement.get("basis"), requirement.get("description", ""))`),
inside `localize_report`, which is imported and called from
`services/api/cadgpt/apps/review/api/v1/serializers.py:95`
(`return localize_report(obj.report)`) — the run-detail response path named in the "Why"
section.

**Docstring parity claim:** corrected/made true. The module docstring now states
explicitly that `requirement_text` is total over any `basis` shape (`None`, a string, a
list, a dict with missing or wrongly-typed keys), the same property `reasons.label_for`
holds over `ReasonCode`, and names the new tests that exercise it — rather than leaving an
implied parity the code did not hold.

**NOT DONE:** nothing in this task's scope. Outside scope, noted only for the record: the
crash chain the "Why" section describes is only fully closed for the `basis` parameter
`requirement_text` receives; `presentation.py`'s `localize_report` itself would still raise
if `report`, a `spec`, or a `requirement` were the wrong shape (e.g. `report.get(...)` on a
non-dict `report`) — out of this task's stated scope
(`services/api/cadgpt/apps/review/requirements.py` and its tests only), and not touched.

## Review
