# T-0040 — `localize_report` must degrade, not 500

**Phase:** 3 — What the first real user needs   **Status:** open
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

<!-- the builder writes this -->

## Review
