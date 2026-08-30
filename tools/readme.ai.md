# readme.ai.md — tools/

## Purpose
`tools/` is the verification harness: the runner behind `make verify`, which is the whole
quality interface of this repository (`CLAUDE.md` §3 and §9). It owns the *mechanism* by
which build gates are registered, ordered, run and reported, and the gates themselves.

`tools/verify.py` is the mechanism and contains no check of its own. Every check lives in
one module under `tools/gates/`, exposing `run() -> GateResult`, plus one entry in
`REGISTRY`. A gate is added by the task that introduces the artefact type it guards, in
that same task (DEC-0022), with a test proving it can reject (DEC-0016).

Nine of the sixteen gates in `docs/architecture/harness.md` are registered today —
1 (lint), 2 (types), 4 (isolation proof), 5 (jurisdiction guard), 6 (placeholder scan),
7 (module contract), 14 (tests), 15 (test balance) and 16 (determinism). `make verify`
prints how many, so the harness's own
coverage is visible rather than assumed — and each gate prints a summary line, so coverage
*inside* a gate is visible on the same terms (DEC-0024). For `mypy` and `pytest` that line
is a count of what was checked. For `ruff check` it is `All checks passed!`, which is the
same string over this repository and over an empty directory and says nothing about how
much was looked at; gate 1's coverage is not visible this way and is not claimed to be.
Gate 4's line is the gate's own and carries both a count and an attribution — how many
packages the `engine` group resolved to, that the inference SDKs raise `ImportError`
there, and which HTTP-capable package arrives through which engine dependency. Gates 5 and
6 name how many files they scanned and under which roots (`"<n> files scanned under
tools/"`, `src/` named too once it exists); gate 7 names how many module directories it
checked. There **is** a partial-coverage question for a full-tree `ast`/filesystem scan —
`REVIEW-harness-p0.md` C1 found it by making gate 15's walk return nothing and watching
`make verify` stay green with an unchanged `GateResult(ok=True, detail='')` — so each of
gates 5, 6 and 7 fails closed instead: a scan root that **exists** but yields zero subjects
is `ok=False`, not a silent pass; a scan root that does not exist (`src/` at P0) is nothing
to scan and stays a clean pass. Gate 15's line is a per-module table, printed on pass and
fail alike; gate 16's names the test count, both seeds and how many tests were deselected,
`unknown` rather than a count when the summary line it comes from did not match (M1).

Gates 1, 2 and 14 re-implement no check. Each wraps an inherited tool (`CLAUDE.md` §6) and
returns the tool's own output unedited: the agent reading a failing `make verify` needs the
real message, not a summary of it. Gates 4, 5, 6 and 7 compose their own verdict, because no
inherited tool answers "is an inference SDK importable in the engine closure", "does an
identifier under `src/` or `tools/` name a jurisdiction", "is this code finished" or "does
this module carry a conforming contract" — gate 4 drives `uv` and a real interpreter and
hands back `uv`'s own words unedited whenever the environment could not be built at all;
gates 5, 6 and 7 parse real files with `ast` (and, for gate 6's comments, `tokenize`) and
report `path:line` and the offending identifier or pattern themselves. What gates 15 and 16
inherit, compose and report is documented as their own module's contract in
`tools/gates/readme.ai.md`, per DEC-0026, not here.

It is **not** part of the product. Nothing under `src/` may import it, and it ships in no
distribution.

## Context
Outside every bounded context in `docs/ddd/03-bounded-contexts.md`. `tools/` is build
infrastructure, not domain code, and models nothing in the problem space.

Subdomain: **generic**. A gate registry has no competitive value; it exists so the other
subdomains can be checked mechanically.

## Contract
The public surface of `tools.verify`. Anything not listed here is internal.

- `GateResult(ok: bool, detail: str)` — frozen dataclass. The outcome of one gate.
  Raises `ValueError` at construction when `ok is False` and `detail` is blank: a failure
  that does not say what failed is not a usable failure.
- `Gate(number: int, name: str, cost: int, run: Callable[[], GateResult])` — frozen
  dataclass. One build guard. `number` is stable and matches the table in
  `docs/architecture/harness.md`. `cost` is 1 (seconds), 2 (tens of seconds) or 3 (minutes).
  `run` takes no arguments and returns a `GateResult`.
- `REGISTRY: list[Gate]` — the single place a gate is registered. There is no other
  registration path, no plugin loader and no injection flag. It currently holds:

  | # | name | cost | module |
  | --- | --- | --- | --- |
  | 1 | `format-and-lint` | 1 | `tools/gates/lint.py` |
  | 2 | `types` | 2 | `tools/gates/types.py` |
  | 4 | `isolation-proof` | 3 | `tools/gates/isolation.py` |
  | 5 | `jurisdiction-guard` | 1 | `tools/gates/jurisdiction.py` |
  | 6 | `placeholder-scan` | 1 | `tools/gates/placeholder.py` |
  | 7 | `module-contract` | 1 | `tools/gates/module_contract.py` |
  | 15 | `test-balance` | 1 | `tools/gates/test_balance.py` |
  | 16 | `determinism` | 2 | `tools/gates/determinism.py` |
  | 14 | `tests` | 3 | `tools/gates/tests.py` |

- `in_cost_order(gates: Sequence[Gate]) -> list[Gate]` — cheapest first, ties broken by gate
  number so a run is deterministic.
- `write_listing(gates: Sequence[Gate], out: TextIO) -> None` — prints one line per gate and
  then `"<n> gates registered"`, running nothing.
- `run_gates(gates: Sequence[Gate], out: TextIO) -> bool` — runs every gate in cost order,
  prints `PASS`/`FAIL` and then, indented by eight spaces, the gate's `detail` whenever that
  detail is non-empty — **on `PASS` as well as `FAIL`** (DEC-0024) — then
  `"<n> gates registered, <m> failed"`. Returns `True` only if every gate passed. Raises
  nothing: a gate that raises is reported `FAIL` with its traceback as the detail, and the
  remaining gates still run. `KeyboardInterrupt` and `SystemExit` propagate — those are the
  operator stopping the run, not a gate reporting a defect.
- `main(argv: list[str]) -> int` — the CLI. Accepts `--list` and nothing else. `--list`
  writes the listing and returns 0; otherwise runs the registry and returns 0 or 1.
  Returns 2 via `argparse` on an unrecognised argument.

The public surface of every gate module — `tools.gates` itself and the seven gate modules
beneath it — is in **`tools/gates/readme.ai.md`**, that module's own contract (DEC-0026).
This file stops at the runner. What the runner needs to know about a gate is the whole of
`Gate`: a number, a name, a cost, and a `run()` returning a `GateResult`. It knows nothing
else about any of them, and neither does this section.

## Invariants enforced here
None from `docs/ddd/04-aggregates-and-invariants.md`: `tools/` is outside the domain model
and owns no domain aggregate.

Three local invariants of the **runner** are enforced here and are not re-checked by
callers. The invariants of a gate — that it reports its tool verbatim, and that an isolation
proof which could not run fails rather than skips — are owned by `tools/gates/` and are
listed in `tools/gates/readme.ai.md`, not here (DEC-0026).

- **A failing gate always carries a detail.** `GateResult.__post_init__`
  (`tools/verify.py`) — a gate cannot construct a silent failure.
- **Every registered gate runs, whatever any other gate does.** `run_gates`
  (`tools/verify.py`) — the `try`/`except Exception` around `gate.run()` means one broken
  gate cannot hide how much else is broken.
- **A gate that checked less than it was asked to says so.** `run_gates`
  (`tools/verify.py`) prints a non-empty detail on `PASS`, and `run_tools`
  (`tools/gates/__init__.py`) makes a succeeding tool's own summary line — the last
  non-empty line of its **stdout** — that detail (DEC-0024). Taking it from stdout and
  stderr merged was the same hole by another route: any line `uv` wrote after the tool
  finished became the gate's summary, so the same gate reported `Installed 12 packages in
  23ms` against a cold tree and `All checks passed!` against a warm one, and the tool's own
  report appeared in neither. A `make verify` whose gate 14 skipped tests is therefore not byte-identical
  to one that ran them. Every link is proven, and so is the chain:
  `test_a_succeeding_command_reports_its_own_last_output_line` runs a real command through
  the real `run_tools` and fails if the surviving line is ever dropped (the hole T-0002b
  closed — one line of `_summary_line` restored the byte-identical silent green while every
  other test stayed green), and
  `test_a_full_run_is_visibly_different_from_a_nested_one` runs the real `make verify` over
  one copied tree twice, plain and marked, and fails if the two printed outputs are the same
  (the hole T-0002c closed — discarding gate 14's success detail in `tools/gates/tests.py`
  left all nineteen tests, `ruff` and `mypy` green).

## Depends on
`tools/verify.py` imports the Python standard library only: `argparse` (the CLI),
`dataclasses` (the two value objects), `traceback` (the detail of a raising gate), `sys`,
`collections.abc`, `typing` — plus `tools.gates`, which is stdlib-only too (`subprocess`,
`pathlib`).

`tools/gates/isolation.py` is the one gate that does not go through `run_tools`. It drives
`uv` directly — `uv export`, `uv venv`, `uv pip install --no-deps`, `uv pip list` and
`uv tree --invert` — and then the interpreter of the environment it has just built, because
what it proves is a property of *that* environment and not of the dev one. It passes neither
`--locked` nor `--frozen`, so a `pyproject.toml` that has drifted from `uv.lock` is resolved
as written: an `openai` added to the `engine` group has to reach the gate for the gate to
mean anything. `uv run --group dev` behaves the same way, so this is not a new licence.
`--no-deps` is passed because the export *is* the closure — every package is already pinned
in it — so re-resolving would ask the index about a set it already has; installing the
exported set exactly is also what the gate then claims to have built.

**Gate 4 needs a warm `uv` cache or a reachable index**, and it is the only gate that needs
more than the dev group. That is inherent: an environment cannot be resolved out of nothing.
It fails closed when it cannot be, and that path has been exercised for real — a `pypi.org`
outage mid-run produced `FAIL  gate 4  isolation-proof` with `error: Request failed after 3
retries` under it and a non-zero `make verify`, not a skip and not a pass.

Nothing third-party is **imported**, on purpose. The gates reach their tools by
`subprocess`, through `uv run --group dev`, at the moment the gate runs. So a missing or
broken toolchain surfaces as *that gate* failing with the real error, not as an import
error before any gate runs. `ruff`, `mypy` and `pytest` are declared in the `dev`
dependency group in `pyproject.toml` (DEC-0005 settled that these three are the static
enforcement layer).

`uvx` is not usable and must not be substituted: it builds an isolated environment with no
dev dependencies, so gate 2 reports `pytest` as a missing library stub for every test
module that imports it, and gate 14 would have no `pytest` at all.

`tools/gates/lint.py`, `types.py`, `tests.py`, `jurisdiction.py`, `placeholder.py` and
`module_contract.py` import `GateResult` under `TYPE_CHECKING` only, and `run_tools`
imports it inside the function body: `tools.verify` imports `tools.gates` to build
`REGISTRY`, so a module-level import back would be a cycle.

`tools/gates/jurisdiction.py`, `placeholder.py` and `module_contract.py` import nothing
beyond the standard library — `ast` and `re` for the first two, `tokenize` and `io`
additionally for `placeholder.py`, `re` and `dataclasses`/`pathlib` throughout. Unlike gate
4 they need no environment and no subprocess: each is a pure parse of real files, which is
what keeps them at cost tier 1.

Tests additionally use `pytest` (dev group) and invoke `make` and the real runner through
`subprocess`.

## Must not depend on
- **Anything under `src/`.** The harness checks the product; a harness importing the thing
  it checks can be broken by the same defect it is meant to catch.
- **Any third-party package at import time.** `python -m tools.verify` must import on a
  clean checkout with nothing installed.
- **Any inference client or model SDK** (I1, I2) — as for every module in this repository.

## Tests
`tools/tests/test_verify.py`, `tools/tests/test_gates_static.py`,
`tools/tests/test_gate_isolation.py`, `tools/tests/test_gate_jurisdiction.py`,
`tools/tests/test_gate_placeholder.py`, `tools/tests/test_gate_module_contract.py` and
`tools/tests/conftest.py`. Fifty-eight tests. The unit/integration split is not written here
as a number: gate 15 computes it at T-0007 from an explicit marker, and a ratio kept in prose
is a ratio that goes stale — this line already had (53, 26/27) when the tree held 58.

Unit, over the runner's own logic (`test_verify.py`) — no process, no filesystem:
- gates run cheapest-first, ties by number;
- `--list` exits 0 and names every registered gate;
- a `GateResult(ok=False)` with a blank detail is rejected at construction;
- a passing gate whose detail is non-empty has that detail printed under its `PASS` line;
- a passing gate whose detail is empty prints its own line and nothing else;
- a gate whose `run` raises is reported `FAIL` with the exception type, its message and its
  traceback in the detail, and the gates after it still run;
- a `CADGPT_VERIFY_DEPTH` that is not a number raises `conftest`'s own `RuntimeError`,
  naming the variable, the value and both decorators — not a bare `ValueError` from `int()`,
  and never read as depth 0, which would apply the cap to a depth the session does not have.

Unit, over one gate's own `run()` (`test_gates_static.py`) — the bad input is planted in a
copied tree, the real tool runs over it, and that gate must return `ok=False` carrying the
tool's words. One gate, one call, nothing of the runner or the `Makefile` involved:
- gate 1 rejects an unused import and its detail contains `F401`;
- gate 2 rejects a contradicted annotation and its detail contains
  `Incompatible types in assignment`;
- gate 14 rejects a failing test and its detail names the failing test.

Unit, over gate 4's rule (`test_gate_isolation.py`) — `isolation.verdict` over a described
closure, because the closure it is about cannot be built by a repository that passes:
- a closure in which an inference SDK imports is `ok=False` and the detail names it, and
  names only it;
- the recorded closure — `requests`, `urllib3`, `flask` and `bcf-client`, each via
  `ifctester`, with no inference SDK — is `ok=True`, and the detail still names every one of
  them and the engine dependency it arrives through. Allowlisted is not forbidden
  (DEC-0023), but it is never silent either.

Unit, over gates 5, 6 and 7's own matching rules (`test_gate_jurisdiction.py`,
`test_gate_placeholder.py`, `test_gate_module_contract.py`) — a pure function
(`findings_in`/`problems_in`) over a constructed source string or package directory, no
filesystem walk and no registry, so each rule is provable from one small snippet:
- a module named for a country fails, a docstring naming one passes, and `iteration`,
  `variance` and `secant` — each a false-positive risk against a naive two-letter ISO
  substring search — all pass (gate 5);
- a `TODO` in a comment fails, a body that is only `pass` fails, a bare
  `raise NotImplementedError` fails, and `raise NotImplementedError("blocked on T-0009")`
  on the first line of a body passes (gate 6);
- a package with no `readme.ai.md` fails, one missing a section fails naming it, one with
  its sections out of order fails, and one with an empty `Open questions` fails (gate 7).

Integration, through the real `Makefile`, the real runner and the real tools:
- `make verify` over this repository exits 0 and prints the registered count;
- a copy of the harness whose `REGISTRY` is reset to one literal failing `Gate(...)` exits
  non-zero;
- that run names the failing gate and prints `"1 gates registered, 1 failed"`;
- each of six bad inputs, planted where the tool scans it, makes a real `make verify`
  exit non-zero and print `FAIL  gate <n>` for exactly the gate it targets — one each for
  gates 1, 2 and 14, plus one each for gates 5, 6 and 7 (an identifier naming a country
  under a copy's `src/`, a `pass`-only function body under `src/`, and a package under
  `src/` with no `readme.ai.md`). Each of those copies registers **only the gate it is
  about** (`conftest.only_gate`), so a proof about gate 1 does not also pay for `mypy` and
  the whole of `pytest` inside the copy. What survives the filter is this repository's real
  registered gate, with its real name, cost and `run`, reached through the copied
  `REGISTRY` itself; nothing any proof asserts changed, and `make verify` went from 133 s
  to 84 s;
- gates 5 and 7 additionally prove that a missing `src/` is a clean pass rather than a
  failure — `src/` does not exist in this repository yet, so each proof copies the harness
  and runs the gate over the copy with no `src/` created in it at all;
- gate 5 additionally proves the same jurisdiction-naming content passes when it sits in a
  comment instead of an identifier, and when it sits under a copy's `packs/` instead of
  `src/` — `packs/` is data (DEC-0020) and this gate never scans it;
- gate 6 additionally proves a `pass` inside an `except` clause passes, and an `...`-only
  body passes inside a `Protocol` and inside a `.pyi` stub — the three shapes a regex
  cannot tell apart from a real stub, which is why gate 6 is built on `ast` structure
  instead;
- gate 7 additionally proves a package directory with no `__init__.py` is skipped rather
  than required to carry a `readme.ai.md`, and that `tools/readme.ai.md` itself, and the
  real tree, both pass;
- **a full `make verify` and a nested one print different output** — the same copied tree
  registering gate 14 only, run twice, once plainly and once with `CADGPT_NESTED_VERIFY=1`
  in the child, with the full run's gate 14 line required to carry a `pytest` summary
  reporting strictly more passes than the nested one's. This is DEC-0024's whole reason for existing, asserted where a
  person reads it. Until T-0002c it was proven only link by link, so discarding gate 14's
  success detail in `tools/gates/tests.py` made a full run byte-identical to a nested one
  again while all nineteen tests passed and `ruff` and `mypy` stayed clean;
- with the nesting marker removed from the environment, the whole of `tools/tests/` runs in
  a child process and reports **no skips at all** — the proof that the nesting guard does
  only what it claims (DEC-0016). That child deselects the two tests that cannot be their
  own subject, and the deselect is **verified at collection time before the child that
  executes anything is started**: `--deselect` with an id matching nothing is silently
  ignored by `pytest` (exit 0, no warning), so a drifting id would let the child run one of
  them, which would spawn its own child — nested processes were observed climbing 8 to 18
  over a minute. A collection-only run executes nothing and so can spawn nothing, and its
  summary must report exactly two deselected tests, matched on a word boundary so that
  `12 deselected` cannot satisfy a check for `2 deselected`;
- this repository's real `engine` group resolves into a real virtualenv in which both
  `anthropic` and `openai` raise `ImportError`, and whose HTTP-capable set is exactly
  `ALLOWED_HTTP` by its recorded paths. This is the assertion
  `docs/ddd/05-import-contracts.md` calls enforcement tier 1: not that nobody wrote the
  import, but that the package is not there to import;
- a **copy** whose `engine` group has `openai` added makes a real `make verify` exit
  non-zero and print `FAIL  gate 4  isolation-proof` with `openai` named in the detail.
  Measured: `exit: 2`, `FAIL  gate 4  isolation-proof`, `openai imports in the engine
  environment.` The copy registers gate 4 only, and this checkout's `pyproject.toml` is
  never touched;
- with the marker **set**, a child reports skips for exactly
  `conftest.SPAWNS_A_RE_ENTERING_PROCESS` and nothing else, compared by node id through the
  child's JUnit XML. This is the pin that makes the previous item mean something: that child
  runs with the marker absent, so `outermost_run_only` is False by construction there and
  only an *unconditional* skip could ever be caught. Until T-0002b the skip set could widen
  back to anything — `outermost_run_only` back on the `ruff` and `mypy` tests left the suite
  green while a marked run skipped half of it.

Integration, through a real subprocess but **not** through the `Makefile` or the runner:
- a real succeeding command run through the real `run_tools` comes back `ok=True` with a
  non-empty `detail` that is **that command's own last output line**. It enters at
  `run_tools` and exits at a real `python` process, which is the layer it is about; the
  outermost-entry-point version of the same property is the full-versus-nested test above;
- a real succeeding command that prints its summary on stdout and is then talked over on
  stderr reports **the stdout line**. Until T-0002d the merged streams let the stderr line
  win, which made the full-versus-nested test's `full.stdout != nested.stdout` assertion
  true by construction — the first run against a cold copy carried `uv`'s install line in
  gate 1's detail and the second did not, so the two runs differed whatever gate 14 did.

**No test writes into this checkout.** `conftest.copied_tree` copies the `Makefile`,
`pyproject.toml`, `uv.lock` and `tools/` into the test's own `tmp_path` and returns the
copy's root; every bad input is planted there, and the gate — or the whole of `make verify`
— runs there. Nothing is cleaned up afterwards and nothing needs to be: the copy goes when
`tmp_path` does. A gate resolves the tree it checks from its own module's location, so the
copy's gate checks the copy; that is why the three `run()` proofs go through
`conftest.gate_result_in`, a process rooted at the copy, rather than calling `run()` in this
one. Nothing is lost: the gate scans its own root either way, and the `Makefile`, the
runner, `ruff`, `mypy`, `pytest` and the bad input are all real. Ten of the twenty-five
tests work this way, and each copy that runs `make verify` registers only the gate its proof
is about. `copied_tree` writes that choice under a marker line at the end of the copy's
`tools/verify.py`, **replacing** any edit already there rather than appending to it: one
level down the tree being copied is itself an edited copy, and two stacked filters would
leave a copy at depth 2 with no gates registered at all. `__pycache__` is the one
thing not copied — it is not source, and a concurrent run writing bytecode into this
checkout renames a temporary file into place, which `shutil.copytree` (which enumerates a
directory before copying it) can see vanish.

Before T-0002c the probes were planted into the real `tools/` under a per-process name, and
every symptom of that was blamed on something else. Three concurrent `make verify` runs
failed six of twelve, *across* gates: one run's lint probe vanishing mid-walk made another
run's gate 2 report `mypy: error: Cannot read file 'tools/unused_import_probe_1377906.py'`.
The same shared tree forced an `ignore` argument onto `shutil.copytree`, left a concurrency
test failing about one run in thirty, dropped probe files in `tools/` whenever a run was
killed, and grew one `__pycache__` entry per run without bound. Planting into a copy removes
the cause, so the per-process names and the `ignore` pattern for them are gone, and
`test_concurrent_verify_runs_do_not_collide` is gone too: with no shared mutable state left
there is nothing for it to detect, and `CLAUDE.md` §7 forbids keeping a test that passes on
ordering luck. Concurrency is instead an acceptance check on the task that changes this
suite — three `make verify` runs at once, all exiting 0.

**The bad inputs live in `tools/tests/badfixtures/`** and are excluded from `ruff` and
`mypy` in `pyproject.toml`; none of their names matches a pytest collection pattern. A
deliberately bad file can therefore sit in the tree, reviewable in a diff, without the
repository failing its own verify — and no gate is disabled to achieve it.

**Nesting is bounded by two markers and capped by a counter, never by a production flag.**
Gate 14 runs `pytest`, so a test that spawns `make verify` (or gate 14's `run()`) spawns
something that runs that test again.

- Most such tests mark the processes they spawn with `CADGPT_NESTED_VERIFY=1`, and a marked
  run skips them (`outermost_run_only`). Recursion stops one level down and the proof still
  runs in full at the depth a person or CI invokes it from.
- Two tests cannot use that marker, because what they are proving is what an *unmarked* run
  does: the full-versus-nested test and the nothing-is-skipped test. They are skipped by
  depth instead (`depth_zero_only`), which is the only thing left that tells their child
  apart from the run a person started.
- Every spawn helper increments `CADGPT_VERIFY_DEPTH` in the child, and a session deeper
  than `conftest.MAX_DEPTH` (2) raises at conftest import, before collecting anything.
  Depth 2 is reached legitimately — an unmarked child at depth 1 runs the tests that spawn
  marked children at depth 2 — and nothing correct goes further. A value that is not a
  number raises the same named error rather than a bare `ValueError` from `int()`.
- **The cap bounds every vector; it names four of the eight.** Removing a skip marker used
  to climb 7 processes to 35 in thirty seconds, killable only by process group, and that is
  over. But only four of the eight tests in `SPAWNS_A_RE_ENTERING_PROCESS` surface a lost
  marker as the cap's own error. The other four — the three
  `test_make_verify_fails_and_names_gate_*` proofs and `test_tests_gate_fails_on_a_failing_test`
  — **pass** with their marker removed, because each asserts on the output of the run it
  started itself, which is there whatever happens below it. Those four are bounded, not
  caught, and what catches them is `test_only_the_spawning_tests_skip_one_level_down`
  comparing the node ids a marked run really skipped against the pinned set. Measured:
  removing `outermost_run_only` from `test_make_verify_fails_and_names_gate_1` leaves that
  test passing and fails three others, `test_only_the_spawning_tests_skip_one_level_down`
  among them.
- A child also does not inherit `VIRTUAL_ENV`. A child rooted at a *copied* tree would
  otherwise be pointed at this checkout's environment for that tree's project — a gate
  checking one tree from inside another tree's virtualenv, which is not the thing under
  test. `uv` says so, printing `does not match the project environment path` on stderr, and
  that is how it was found: `_summary_line` took the warning as the gate's summary in place
  of `pytest`'s counts, and both runs' gate 14 reported the warning and nothing else. That
  symptom is closed at its source now — a success summary comes from stdout — so this entry
  is no longer what stands between the suite and a wrong summary. It stays because handing a
  child another tree's virtualenv is wrong on its own terms.

**Neither of gate 4's integration proofs carries a nesting marker, and neither belongs in
`SPAWNS_A_RE_ENTERING_PROCESS`.** One calls `isolation.resolve()` in this process; the other
runs `make verify` over a copy registering gate 4 alone, and gate 4 drives `uv` and a
throwaway interpreter, not this suite, so it cannot re-enter the harness. They are the same
case as the two tests that drive `ruff` and `mypy`: a test skipped for a reason untrue about
it is a proof silently lost. The consequence is that both run again inside every child this
suite spawns, which is what gate 14 going from 83 s to 142 s is mostly made of.

The marker names, the depth counter, both decorators and the `copied_tree`, `make_verify`,
`run_pytest` and `gate_result_in` helpers are defined **once**, in `tools/tests/conftest.py`,
and nowhere in `tools/verify.py` or `tools/gates/`: the runner has exactly one registration
path and gains no test-only surface, no flag and no env read.
`SPAWNS_A_RE_ENTERING_PROCESS` in the same file names, by node id, exactly the eight tests
skipped one level down, so that set is checked rather than remembered. `only_gate` and the
registry-edit marker live there too. The two tests that
drive `ruff` and `mypy` carry no marker — those tools are not this suite and cannot recurse,
and a test skipped for a reason untrue about it is a proof silently lost.

The guard is spoofable, and DEC-0024 accepts that and makes its effect visible instead:
gate 14 reports `pytest`'s summary line, so `env CADGPT_NESTED_VERIFY=1 make verify` prints
`19 passed, 6 skipped` where a full run prints `25 passed`. **`make verify` alone is
therefore not evidence that this suite ran in full** — that is why every task also runs
`uv run --group dev pytest tools/tests/ -q` directly, and why one test asserts the suite
reports zero skips when the marker is absent.

All three test modules import the shared pieces as `from tools.tests.conftest import ...`,
not `from conftest import ...`. `tools/` is a package, so `mypy --strict tools/` names that file
`tools.tests.conftest`; the bare spelling works under `pytest` and fails gate 2 with
`Cannot find implementation or library stub for module named "conftest"`.

**Mocking: none.** No fake gate module is imported, no filesystem is faked, `make` is
invoked as `make`, and `ruff`, `mypy` and `pytest` are the real tools over real files.

## How to run it
```
$ make verify
python3 -m tools.verify
PASS  gate 1  format-and-lint
        All checks passed!
        11 files already formatted
PASS  gate 2  types
        Success: no issues found in 11 source files
PASS  gate 4  isolation-proof
        51 packages resolved from the engine group; anthropic, openai raise ImportError there; HTTP-capable present: requests via ifctester, urllib3 via ifctester, flask via ifctester, bcf-client via ifctester
PASS  gate 14  tests
        ======================== 25 passed in 142.43s (0:02:22) ========================
4 gates registered, 0 failed
$ echo $?
0
```

Gate 4's line is the one a customer or a regulator is shown, and it is the whole claim: this
many packages resolved from the `engine` group, no inference SDK importable among them, and
each HTTP-capable package present named with the engine dependency that forces it.

Gate 4 itself costs under a second against a warm `uv` cache — a virtualenv built from
hardlinked wheels — and tens of seconds the first time, when the closure has to be
downloaded. It is cost 3 because that cold case is real, not because the warm one is slow.

Gate 14 dominates the run because this suite drives the whole harness against copies of it:
ten of the twenty-five tests run a real `make verify` or a real gate over a tree they copied
first. That is its cost 3, and it is the price of proving the gates instead of asserting
them. Each of those copies registers only the gate its proof is about, which is what took
`make verify` from 133 s to 84 s; the copy in the gate 14 proofs still runs a real `pytest`
over itself, and that is the floor. Gate 4's two integration proofs then took gate 14 from
83 s to 142 s: they carry no nesting marker, correctly, so they run again in every child.

Each `PASS` carries its tool's own summary line, so a run that checked less than it should
is visible as one (DEC-0024) — gate 14's line is a count, gate 1's `All checks passed!` is
not. One level down, inside a process this suite spawned, the same command reports the
difference:

```
$ env CADGPT_NESTED_VERIFY=1 make verify
python3 -m tools.verify
PASS  gate 1  format-and-lint
        All checks passed!
        11 files already formatted
PASS  gate 2  types
        Success: no issues found in 11 source files
PASS  gate 4  isolation-proof
        51 packages resolved from the engine group; anthropic, openai raise ImportError there; HTTP-capable present: requests via ifctester, urllib3 via ifctester, flask via ifctester, bcf-client via ifctester
PASS  gate 14  tests
        ================== 19 passed, 6 skipped in 102.78s (0:01:42) ===================
4 gates registered, 0 failed
```

A genuine child skips eight, not six: it carries the depth counter as well as the marker, so
the two `depth_zero_only` tests skip there too. Exporting the marker by hand, as above, only
reaches the six that read it — and that is still visibly not a full run, which is all
DEC-0024 asks of it.

Listing without running anything:

```
$ python3 -m tools.verify --list
gate 1  cost 1  format-and-lint
gate 2  cost 2  types
gate 4  cost 3  isolation-proof
gate 14  cost 3  tests
4 gates registered
```

A failure prints the tool's own message, in full and unedited, indented under the gate that
produced it — the success lines above are summaries, a failure never is:

```
FAIL  gate 2  types
        $ uv run --group dev mypy --strict tools/
        exited 1
        tools/mismatched_annotation_probe.py:14: error: Incompatible types in assignment (expression has type "int", variable has type "str")  [assignment]
        Found 1 error in 1 file (checked 10 source files)
```

## Open questions
- Seven gates of sixteen are registered. A green `make verify` today means the tree is
  lint-clean, type-clean under `--strict`, its tests pass, no inference SDK is resolvable
  in the `engine` dependency closure, no identifier under `src/` or `tools/` names a
  jurisdiction, no placeholder pattern is left in under `src/` or `tools/`, and every module
  directory under `src/` or `tools/` — every package, at any depth, outside a `tests/` tree —
  carries a conforming `readme.ai.md` — and nothing more.
  `src/` still does not exist, so gates 5, 6 and 7 are proven by their fixtures rather than
  by anything real found under `src/` today (DEC-0016); the one thing gate 7 finds in the
  real tree is `tools/readme.ai.md` itself. `docs/architecture/harness.md` names all sixteen
  gates and when each becomes real.
- **`JURISDICTION_TOKENS` (gate 5) is a starting set, not an exhaustive one.** It covers the
  countries and code bodies named explicitly by T-0004 plus enough neighbours to be useful,
  deliberately without bare two-letter ISO codes (the false-positive guard in
  `tools/gates/jurisdiction.py`'s own docstring). Extending it for a jurisdiction not yet
  covered is a one-line addition to the set, not a design change.
- **Gate 7's rule was reopened and is now DEC-0026: every package directory except a
  `tests/` tree.** It shipped at T-0006 checking only the *topmost* `__init__.py` on a path,
  which would have checked `src/engine/` and skipped all seven `src/engine/*` contexts
  `docs/architecture/module-map.md` names. The narrowing came from the session building the
  gate, and was exactly what made that session's own tree pass — the failure mode this
  repository is built around. `tools/gates/` now carries its own `readme.ai.md` as a result.
  What is still untested is `src/`: DEC-0026 expects `src/engine` to be reported as a module
  directory in its own right if it carries an `__init__.py`, and the first `src/` task is
  where that meets a real layout.
- **DEC-0023 is closed**, not open, and gate 4 ships to its terms: it does **not** close the
  raw-HTTP path. `ifctester` is a forced inherited component and pulls `requests`, `urllib3`,
  `flask` and `bcf-client` into the engine closure, so gate 4 asserts instead that no
  inference SDK resolves and that every HTTP-capable package in the closure is on the
  allowlist by its recorded path. The raw-HTTP path is closed by **gate 3** (import
  contracts), which forbids `src/engine` from importing any HTTP client or socket module, and
  gate 3 ships at **C1.1** — it cannot exist before there is an `src/` package to constrain.
  Until C1.1 that path is unguarded, and that is known and scheduled, not overlooked.
- **Gate 4 reads the `engine` group's resolved closure, not what `src/engine` will import.**
  A distribution boundary is only a proof for code that actually ships inside it, and no code
  ships in `cadgpt-engine` yet. What the gate guarantees today is the environment; what makes
  that guarantee load-bearing is `src/engine` existing and being packaged from this group,
  which is C1.1's work.
- Gate 2 checks `tools/` and gate 14 collects the whole repository. The first `src/` task
  must extend gate 2's paths in that same task, or `src/` will be type-checked by nothing
  while `make verify` stays green.
- **Two things this suite still touches in this checkout, neither of them content.**
  `test_make_verify_over_the_real_tree_exits_zero` runs a real `make verify` here on
  purpose, and the real `mypy` and `pytest` refresh `.mypy_cache/` and `.pytest_cache/` when
  they run. Measured across a full `pytest tools/tests/ -q`: exactly three cache paths
  change mtime and nothing else — no file is created, modified or deleted anywhere under
  version control, and `git status --porcelain` is byte-identical before and after. Removing
  even that would mean dropping the one test that runs the harness over this tree, which is
  worth more than the last of the isolation.
- **Two of the eight pinned re-entering tests may no longer re-enter.** With their copies
  narrowed to one gate, `test_make_verify_fails_and_names_gate_1` runs only `ruff` in its
  copy and `..._gate_2` only `mypy`; neither spawns `pytest` any more, so neither can run
  this suite again. They still carry `outermost_run_only` and are still in
  `SPAWNS_A_RE_ENTERING_PROCESS`, because T-0002d was a cost change and changing the skip
  set is a behaviour change — and `test_gates_static`'s own docstring says a test skipped for
  a reason untrue about it is a proof silently lost. Whether to drop those two markers is a
  decision for the Lead, not something to slip into a cost task.
- **The depth cap is a backstop, not a design.** `MAX_DEPTH = 2` is derived from how this
  suite nests today: an unmarked child at depth 1 runs the tests that spawn marked children
  at depth 2. A future test that legitimately needs a third level will hit it, and the right
  response is to re-derive the bound in `conftest.MAX_DEPTH`'s docstring — not to raise the
  number until the suite stops complaining.
