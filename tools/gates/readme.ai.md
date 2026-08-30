# readme.ai.md — tools/gates/

## Purpose
The build gates themselves: one module per gate, each exposing `run() -> GateResult`, plus
the shared machinery for invoking an inherited tool and reporting what it said. This module
holds every **check**. It holds no scheduling, no ordering, no reporting and no CLI — those
are `tools.verify`'s, and a gate that reached for them would be a gate deciding when it runs.

It is a module of its own, and not a section inside `tools/readme.ai.md`, because the two
boundaries are genuinely different (DEC-0026). The runner's contract is four fields and a
callable. A gate's contract is what it scans, what it refuses to scan, what its rule data
means and what an extension to that data costs — and there are nine of them. Splitting the
two is what keeps either file short enough to be read instead of the code, which is the whole
point of the convention.

**No gate here re-implements a check** (`CLAUDE.md` §6, inherit before writing). Gates 1, 2
and 14 wrap `ruff`, `mypy` and `pytest` and hand the tool's own output back unedited. Gates 5,
6 and 7 have no tool to inherit — there is no off-the-shelf checker for "no identifier under
`src/` names a jurisdiction" — and are `ast`/filesystem scans written here. Gate 4 drives
`uv` to build a real environment and asks it a question no static tool can answer. Gate 15
inherits `pytest --collect-only` to classify tests by their own marker rather than re-parsing
test files itself; gate 16 inherits `pytest` a second time, with `pytest-randomly` (DEC-0027
§3) doing the order-varying no gate here would want to author.

## Context
Bounded context: **none**. `tools/` is outside the domain model entirely
(`docs/ddd/03-bounded-contexts.md` names ten contexts; this is not one of them). It is build
infrastructure, and the one part of the repository the domain does not reach into.

Subdomain: **generic**, for the same reason as `tools/` as a whole — a lint wrapper and a
directory walker have no competitive value. What is not generic is *which* rules are encoded
here: gates 4, 5, 6 and 7 exist because of this product's specific invariants (I1, I4, and
the definition of done), and their rule data is the part worth reading carefully.

## Contract
The public surface of `tools.gates`:

- `run_tools(commands: Sequence[Sequence[str]]) -> GateResult` — runs each command through
  `uv run --group dev` from the repository root and fails if any exited non-zero. Every
  command runs even after one has failed. The detail of a failure is the invocation, the
  exit code and the tool's own stdout and stderr, unedited — on a failure you want
  everything. The detail of a success is one line per command: that command's **last
  non-empty line of stdout**, and stdout only. `ruff`, `mypy` and `pytest` all summarise on
  stdout; stderr carries whoever ran them talking — `uv` announcing `Installed 12 packages
  in 23ms` against a cold environment, or warning that a virtualenv does not match the
  project — and reading the two streams merged let any such line displace the tool's own
  report and become the gate's summary. For `mypy`
  (`Success: no issues found in N source files`) and `pytest` (`N passed`) that line
  carries a count of what was checked; for `ruff check` it is `All checks passed!`, a
  constant that carries no count. What the line is reliably good for is making one run
  *differ* from another — a gate 14 that skipped its proofs reports a different line from
  one that ran them (DEC-0024) — not for reading gate 1's coverage off. A command that
  printed nothing on stdout contributes no line, so a gate with nothing to report stays
  silent. Gate 1 runs two commands and so reports two lines.
- `lint.run() -> GateResult` — gate 1. `ruff check .` and `ruff format --check .`. A tree
  can satisfy either half while failing the other, so both run.
- `types.run() -> GateResult` — gate 2. `mypy --strict tools/`. The task that creates the
  first `src/` package extends the paths, in that same task.
- `tests.run() -> GateResult` — gate 14. `pytest` with no path, so it collects whatever the
  repository holds rather than a list that has to be remembered.

The public surface of `tools.gates.isolation` — gate 4, the isolation proof (DEC-0004,
DEC-0023). It is the only gate with a surface of its own, because its rule is data:

- `FORBIDDEN_IN_ENGINE: tuple[str, ...]` — `("anthropic", "openai")`. Importing one of these
  in the engine environment must raise `ImportError`.
- `HTTP_CAPABLE: tuple[str, ...]` — every distribution we know can open a socket. Presence
  is not itself a failure.
- `ALLOWED_HTTP: tuple[tuple[str, str], ...]` — `(package, reached_via)` pairs. Today
  `requests`, `urllib3`, `flask` and `bcf-client`, each via `ifctester`. `reached_via` is the
  declared **member of the `engine` group** the package is reached through, not its immediate
  parent: `urllib3` arrives under `requests` under `bcf-client`, and what the ratchet is about
  is which engine dependency is responsible for the whole path. Adding a pair is a decision
  record (DEC-0023).
- `ENGINE_GROUP: str` — `"engine"`, the dependency group in `pyproject.toml` that is
  `cadgpt-engine`.
- `ResolvedEngineEnvironment(package_count: int, inference_sdks_importable: tuple[str, ...],
  http_capable_reached_via: tuple[tuple[str, tuple[str, ...]], ...])` — frozen dataclass.
  What a real, built engine environment turned out to contain.
- `resolve() -> ResolvedEngineEnvironment` — exports the `engine` group, builds a throwaway
  virtualenv from it under a temporary directory, imports each `FORBIDDEN_IN_ENGINE` name in
  *that* interpreter, lists what was installed, and attributes each installed `HTTP_CAPABLE`
  package to the engine dependencies it arrives through (`uv tree --invert`). Raises on any
  step that does not complete, carrying that step's invocation, exit code and output.
- `verdict(environment: ResolvedEngineEnvironment) -> GateResult` — the whole of the gate's
  rule and nothing else. Public because the case gate 4 exists for — an engine environment
  that *does* import an inference SDK — is the one case a repository passing its own verify
  cannot build, so the rule has to be reachable without building it.
- `run() -> GateResult` — `verdict(resolve())`, with a failed resolution turned into
  `ok=False` carrying the resolver's own message. **Never a skip:** an isolation proof that
  could not run has proved nothing, and saying so is the only honest report of it.

Rule selection, line length and the exclusions for `ruff` and `mypy` are configured in
`pyproject.toml` and nowhere else — one place, no per-tool config files. The selection
includes `RUF100` (unused `noqa`) **alongside** the real rule set, because `CLAUDE.md`
forbids suppressing a warning, so every surviving `noqa` must be load-bearing. `RUF100`
selected on its own reports every other rule as non-enabled and so calls live suppressions
dead; it is only meaningful next to the rules it is checking against.

The public surface of `tools.gates.jurisdiction` — gate 5, the jurisdiction guard (I4,
DEC-0020). Enforces I4 mechanically: a country, code body or clause reference may not
appear in an **identifier** under `src/` or `tools/`; `packs/` is data and is never scanned.

- `JURISDICTION_TOKENS: frozenset[str]` — whole-segment tokens (country names, ISO 3166-1
  alpha-3 codes, named code-body acronyms). Bare two-letter alpha-2 codes are deliberately
  absent: a naive match against one turns almost any English word into a false positive
  (`iteration` opens with `IT`, Italy's code), which is exactly the class of failure the
  false-positive guard in the module docstring exists to name. Extend by adding a lowercase
  whole word here.
- `token_in(identifier: str) -> str | None` — the jurisdiction token `identifier` names, or
  `None`. Splits the identifier into lowercase snake/camel/digit segments and matches a
  **whole segment** against `JURISDICTION_TOKENS`, or a code word immediately followed by a
  digit segment (`clause_5_3_2`, `art14`, `sec_302`) against the clause-reference shape —
  never a substring search.
- `findings_in(source: str, path: Path) -> list[Finding]` — every jurisdiction-naming
  identifier in one file's source: the module's own file name, every class, function and
  parameter name, every assignment target, and every string used as a dict key. A pure
  function over source text — no filesystem walk — so the matching rule is provable from a
  single constructed snippet.
- `Finding(path: Path, line: int, identifier: str, token: str)` — frozen dataclass. One
  offending identifier, where it was found and which token it names.
- `run() -> GateResult` — walks every `*.py` file under `src/` and `tools/` (a missing
  `src/` is nothing to scan, not a failure — it does not exist yet at P0) and reports every
  finding as `path:line: identifier ... names jurisdiction token ...`.

The public surface of `tools.gates.placeholder` — gate 6, the placeholder scan
(`docs/process/definition-of-done.md` condition 4). Four patterns, under `src/` and
`tools/`: a `TODO`/`FIXME`/`XXX`/`HACK` marker in a real `#` comment; a function body that
is only `pass` (or only `...`, unless the enclosing class is a `Protocol` or the file is a
`.pyi` stub); `"placeholder"`/`"not implemented"`/`"dummy"` as the **direct** value of a
`return` or an assignment; and a `raise NotImplementedError` that is bare or is not the
first statement (after an optional docstring) of its function body.

- `PLACEHOLDER_VALUES: frozenset[str]` — the three stand-in values, matched
  case-insensitively as a whole string, never a substring.
- `findings_in(source: str, path: Path) -> list[Finding]` — every placeholder pattern in
  one file's source. A pure function over source text, structural (`ast` for the body and
  raise shapes, `tokenize` for comments) rather than a regex over the whole file — a regex
  cannot tell a stub `pass` from one legitimately doing nothing inside an `except` clause.
- `Finding(path: Path, line: int, identifier: str, pattern: str)` — frozen dataclass.
- `run() -> GateResult` — walks every `*.py` file under `src/` and `tools/` and reports
  every finding as `path:line: pattern (identifier)`.

The public surface of `tools.gates.module_contract` — gate 7, the module contract checker
(DEC-0011, `docs/process/readme-ai-convention.md`). Checks presence and conformance of
`readme.ai.md`, never content quality.

- `REQUIRED_SECTIONS: tuple[str, ...]` — the nine fixed section names, in the fixed order,
  from `docs/process/readme-ai-convention.md`. Reordering this is a change to the
  convention and a decision record, not a task-level edit.
- `problems_in(directory: Path) -> list[str]` — everything wrong with `directory`'s
  `readme.ai.md`: missing entirely, missing a named section, sections present but out of
  order, or a section with an empty body — or an empty list if it conforms. A pure function
  over one directory, so each rule is provable from a single constructed package.
- `module_directories(root: Path) -> list[Path]` — every directory under `root` carrying an
  `__init__.py`, at any depth, sorted, with `tests/` and `__pycache__` trees not entered at
  all. A missing `root` is an empty list, not an error.
- `EXCLUDE_DIR_NAMES: frozenset[str]` — `{"__pycache__", "tests"}`. A module's test tree is
  part of that module's contract, not a module with a contract of its own.
- `run() -> GateResult` — checks every module directory under `src/` and `tools/`
  (DEC-0026). Finding a package is **not** a reason to stop descending: a package nested
  inside another is its own module and owes its own contract, which is what makes this gate
  reach `src/engine/ingest`, `src/engine/derivation` and the five other contexts
  `docs/architecture/module-map.md` names rather than stopping at `src/engine/`. `src/` does
  not exist yet at P0, so the gate is proven by its fixtures rather than by its scan target
  (DEC-0016); what it finds in the real tree today is `tools/readme.ai.md` and this file.

The public surface of `tools.gates.test_balance` — gate 15, test balance (DEC-0010,
`docs/process/testing-strategy.md`). Per module, counts unit versus integration tests and
fails outside a 40-60% integration ratio; classification comes from `@pytest.mark.integration`
alone, never from a file's path or name.

- `MIN_INTEGRATION_RATIO`, `MAX_INTEGRATION_RATIO` — `0.40`, `0.60`.
- `MIN_TESTS_TO_ENFORCE: int` — `4`. Below this many tests a module's ratio is reported but
  never fails the gate — a ratio over so few tests is noise, not signal.
- `ModuleCounts(module: str, unit: int, integration: int)` — frozen dataclass. `module` is a
  path relative to the repository root. `total`, `integration_ratio`, `enforced` and
  `in_band` are derived properties, not stored fields.
- `verdict(counts: list[ModuleCounts]) -> GateResult` — the whole of the rule, over
  already-computed counts. Pure: a constructed list proves every rule directly, with no
  filesystem or subprocess involved. `detail` is the per-module table, on PASS as well as
  FAIL (DEC-0024).
- `run() -> GateResult` — `verdict` over real counts. A module is in scope when it is a
  module directory (`tools.gates.module_contract.module_directories`, DEC-0026) that owns its
  own `tests/` subdirectory; `tools/gates` shares `tools/tests/` with its parent rather than
  owning a tree of its own, so only `tools` is in scope until that changes. Counts come from
  two real `pytest --collect-only -q` invocations (`-m integration` and `-m "not integration"`)
  — collection only, so this gate cannot itself execute a test body or spawn anything a test
  body would.

The public surface of `tools.gates.determinism` — gate 16, determinism (DEC-0027). Runs the
suite twice, varying `PYTHONHASHSEED` and collection order, and fails if the two runs
disagree about any test's outcome. The eight tests that spawn a process re-entering this
harness (`tools/tests/conftest.SPAWNS_A_RE_ENTERING_PROCESS`) carry a `spawns_harness` marker,
applied by a `pytest_collection_modifyitems` hook in `tools/tests/conftest.py` rather than by
this module, and are deselected from both runs (`-m "not spawns_harness"`, DEC-0027 §1) —
this module does not import that frozenset, because a gate must not depend on the test suite
it checks.

- `DESELECT_MARKER: str` — `"spawns_harness"`.
- `RunResult(passed: frozenset[str], failed: frozenset[str], deselected: int)` — frozen
  dataclass. One pytest run's outcome.
- `verdict(first: RunResult, second: RunResult, seeds: tuple[str, str]) -> GateResult` — the
  whole of the rule, over two already-computed runs. Pure, for the same reason
  `test_balance.verdict` is. `detail` names every disagreeing test on FAIL, and reports the
  test count, both seeds and the deselected count on PASS too (DEC-0024, DEC-0027 §4).
- `execute(*, hash_seed: str, random_seed: int, report: Path, cwd: Path = REPO_ROOT) ->
  RunResult` — one real, unmocked `pytest` subprocess with `spawns_harness` deselected,
  `-p randomly --randomly-seed=<random_seed>` and `PYTHONHASHSEED=<hash_seed>`, reported
  through a real JUnit report. `cwd` defaults to this repository, which is what the
  registered gate always uses; a test proving this module's own rule points it at a small
  constructed fixture directory instead, so a proof of gate 16 never re-enters the suite it
  is defined in.
- `run() -> GateResult` — `execute` twice, with two fixed (not random — `CLAUDE.md` §7
  forbids unpinned randomness in a proof) `PYTHONHASHSEED`/`-p randomly` seed pairs, then
  `verdict`.

## Invariants enforced here
None from `docs/ddd/04-aggregates-and-invariants.md` — this module owns no domain aggregate.

Two product invariants are *guarded* here, which is not the same as owned:

- **I1 / I2** — `isolation.run` (gate 4) proves that a real `engine` environment cannot import
  an inference SDK. It does not enforce I1; the dependency graph in `pyproject.toml` does. The
  gate is what makes the enforcement observable and stops it silently decaying.
- **I4** — `jurisdiction.run` (gate 5) fails the build when an identifier under `src/` or
  `tools/` names a country, code body or clause reference. `packs/` is data and is never
  scanned, because a jurisdiction's rules are exactly where a jurisdiction's name belongs.

Two invariants of the gate mechanism itself are enforced here and are not re-checked by
`tools.verify`:

- **A gate reports its tool verbatim.** `run_tools` — the failure detail is the tool's own
  stdout and stderr, never a summary of them. `isolation` does not use `run_tools` and holds
  the same line itself: every `uv` step it drives reports its invocation, exit code and output
  unedited on failure.
- **An isolation proof that could not run fails.** `isolation.run` — never a skip. A proof
  that did not execute has proved nothing, and `ok=False` is the only honest report of it.
  This is the single place gate 4's fail-closed behaviour lives.

## Depends on
- `tools.verify` — for `GateResult` only, and **imported inside each function, never at module
  level**. `tools.verify` imports this package to build `REGISTRY`, so a module-level import
  here is a cycle. `TYPE_CHECKING` blocks carry the annotation.
- `subprocess`, `pathlib`, `ast`, `tokenize`, `re`, `json`, `tempfile`, `os`,
  `xml.etree.ElementTree` — the standard library does all of the scanning. No third-party
  dependency is added for a gate.
- `uv`, on `PATH` — every inherited tool is invoked as `uv run --group dev <tool>` so it
  resolves from the `dev` group in `pyproject.toml`. Gate 4 additionally drives `uv export`,
  `uv venv`, `uv pip install` and `uv tree`.
- `ruff`, `mypy`, `pytest` — inherited, in the `dev` group, invoked never imported. `pytest`
  additionally needs `pytest-randomly` (also in the `dev` group, DEC-0027 §3) for gate 16's
  two `-p randomly` runs; every other invocation of `pytest` anywhere carries
  `-p no:randomly` from `pyproject.toml`'s `addopts` and is unaffected by its presence.
- `tools.gates.module_contract` — gate 15's `_modules_with_tests` reuses
  `SCAN_ROOTS`/`module_directories`, the same walk gate 7 uses to find module directories, so
  the two gates agree on what a module is without either re-implementing the other's walk.

## Must not depend on
- **Anything under `src/`.** A gate that imported the code it checks could not report on a
  tree that fails to import, which is precisely the tree it exists to report on. Every gate
  reads source as text or as `ast`, and gate 4 reads a resolved environment — none imports the
  subject.
- **`tools.verify` at module level.** A cycle; see Depends on.
- **Any environment variable, flag or config key that changes what a gate checks.** T-0001a
  removed the runner's injection path deliberately. The gates have no equivalent and must not
  grow one: a gate whose scope can be narrowed from outside is a gate that can be turned off.
  `tools/tests/conftest.py`'s nesting markers are a property of the *tests* and are read by
  neither `tools.verify` nor anything here.
- **`uvx`.** It builds an isolated environment with no dev dependencies, so gate 2 would report
  `pytest` as a missing stub for every test module and gate 14 would have no `pytest` at all.

## Tests
In `tools/tests/`, which is `tools/`'s test tree and covers this module too — one contiguous
directory, per `docs/architecture/module-map.md`. Gate 7 does not treat it as a module
(DEC-0026).

| File | Proves |
| --- | --- |
| `test_gates_static.py` | Gates 1, 2 and 14 reject: a lint error, a type error and a failing test each fail `make verify` in a copied tree. |
| `test_gate_isolation.py` | Gate 4's rule (`verdict`) over a constructed `ResolvedEngineEnvironment`, and a real `resolve()` against this repository's `engine` group. |
| `test_gate_jurisdiction.py` | Gate 5's matching rule over constructed snippets, and a planted jurisdiction-named identifier failing the real gate. |
| `test_gate_placeholder.py` | Gate 6's four patterns, and each one planted in a copied tree. |
| `test_gate_module_contract.py` | Gate 7's four conformance rules, the walk itself, and a bad package planted **beneath** a conforming one. |
| `test_verify.py` | The runner, not the gates — registration, cost order, a raising gate, the nesting guards. |
| `test_gate_test_discipline.py` | Gate 15's `verdict` over constructed `ModuleCounts` (a skewed module fails, a balanced one passes, a too-small one is reported not failed, the table survives a pass); gate 16's `execute`/`verdict` over small real fixture directories (a `PYTHONHASHSEED`-dependent test disagrees and is named, a stable fixture with a `spawns_harness`-marked test passes and reports what it deselected); a fresh, unedited `conftest.copied_tree` lists nine registered gates. |

**Mocking: none.** Every gate is proven against real files, a real `Makefile` and real
`ruff`/`mypy`/`pytest`. Gate 4 builds a real virtualenv. The only isolation is
`conftest.copied_tree`, which copies the harness into `tmp_path` so a rejection proof plants
its bad input somewhere other than this checkout — a real end-to-end run against a tree that
is simply not this one. Gates 15 and 16's own proofs use the same lever for a different
reason: a small constructed fixture, or a fresh copy, so a proof of either gate never re-enters
`tools/tests/`, the tree it is defined in.

The unit/integration split is not stated here as a number, deliberately: gate 15 computes it
and prints it, and a number written into prose is a number that goes stale. T-0007a marked
every pre-existing test in `tools/tests/` by what it actually does — one function's logic
over constructed input is unit; copying a tree, spawning `make verify` or `pytest`, running a
real `ruff`/`mypy`, building a real environment, or driving a gate's own `run()` over this
repository's real filesystem is integration — and gate 15 now passes over `tools`, in band
(`decisions/DEC-0029-gate-15-classification.md`, decided).

## How to run it
Any single gate, without the rest of the harness:

```
$ uv run --group dev python -c "from tools.gates import module_contract; print(module_contract.run())"
GateResult(ok=True, detail='')
```

The walk gate 7 performs, over the real tree:

```
$ uv run --group dev python -c "from pathlib import Path; from tools.gates import module_contract as m; print([str(p) for p in m.module_directories(Path('tools'))])"
['tools', 'tools/gates']
```

Two entries, not one — that is DEC-0026 in effect, and the topmost-only rule it replaced
printed `['tools']`.

Gate 16, in isolation, against a small real fixture rather than `tools/tests/` itself:

```
$ uv run --group dev python -c "
from pathlib import Path
from tools.gates import determinism as d
r1 = d.execute(hash_seed='1', random_seed=1000003, report=Path('/tmp/a.xml'), cwd=Path('fixture'))
r2 = d.execute(hash_seed='2', random_seed=2000017, report=Path('/tmp/b.xml'), cwd=Path('fixture'))
print(d.verdict(r1, r2, seeds=('1', '2')))
"
```

All nine, in cost order, through the real entry point:

```
$ make verify
```

## Open questions
- **`JURISDICTION_TOKENS` (gate 5) is a starting set, not an exhaustive one.** It covers the
  countries and code bodies T-0004 named plus enough neighbours to be useful, deliberately
  without bare two-letter ISO codes. Extending it is a one-line addition, not a design change.
- **Gate 7 has never run against a real `src/` tree**, because there is none. DEC-0026 expects
  every `src/engine/*` context to be reported as its own module directory, including
  `src/engine` itself if it carries an `__init__.py`. The first `src/` task is where that
  expectation meets a real layout; it should read DEC-0026's Reopens-if before assuming.
- **Gate 3 (import contracts) is not here and cannot be**, until `src/` exists to constrain.
  Until then the raw-HTTP path out of the engine is unguarded — gate 4 proves no inference SDK
  resolves, not that nothing opens a socket. Known and scheduled at C1.1, not overlooked.
- **Gates 8–13 are unwritten.** `docs/architecture/harness.md` names all sixteen and when each
  becomes real.
- **Gate 15's only subject is `tools` itself.** It reports `32 unit / 33 integration (51%
  integration, in band)`, from markers a person applied by reading each test (T-0007a,
  DEC-0029). One module in band is not evidence the band is right; the first `src/` module is
  the first independent test of that, and DEC-0029's Reopens-if is what to read if it lands
  outside.
