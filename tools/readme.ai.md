# readme.ai.md — tools/

## Purpose
`tools/` is the verification harness: the runner behind `make verify`, which is the whole
quality interface of this repository (`CLAUDE.md` §3 and §9). It owns the *mechanism* by
which build gates are registered, ordered, run and reported, and the gates themselves.

`tools/verify.py` is the mechanism and contains no check of its own. Every check lives in
one module under `tools/gates/`, exposing `run() -> GateResult`, plus one entry in
`REGISTRY`. A gate is added by the task that introduces the artefact type it guards, in
that same task (DEC-0022), with a test proving it can reject (DEC-0016).

Three of the sixteen gates in `docs/architecture/harness.md` are registered today —
1 (lint), 2 (types) and 14 (tests). `make verify` prints how many, so the harness's own
coverage is visible rather than assumed — and each gate prints its tool's own summary
line, so coverage *inside* a gate is visible on the same terms (DEC-0024). For `mypy` and
`pytest` that line is a count of what was checked. For `ruff check` it is `All checks
passed!`, which is the same string over this repository and over an empty directory and
says nothing about how much was looked at; gate 1's coverage is not visible this way and
is not claimed to be.

No gate re-implements a check. Each wraps an inherited tool (`CLAUDE.md` §6) and returns
the tool's own output unedited: the agent reading a failing `make verify` needs the real
message, not a summary of it.

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

Rule selection, line length and the exclusions for `ruff` and `mypy` are configured in
`pyproject.toml` and nowhere else — one place, no per-tool config files. The selection
includes `RUF100` (unused `noqa`) **alongside** the real rule set, because `CLAUDE.md`
forbids suppressing a warning, so every surviving `noqa` must be load-bearing. `RUF100`
selected on its own reports every other rule as non-enabled and so calls live suppressions
dead; it is only meaningful next to the rules it is checking against.

## Invariants enforced here
None from `docs/ddd/04-aggregates-and-invariants.md`: `tools/` is outside the domain model
and owns no domain aggregate.

Three local invariants of the harness itself are enforced here and are not re-checked by
callers:

- **A failing gate always carries a detail.** `GateResult.__post_init__`
  (`tools/verify.py`) — a gate cannot construct a silent failure.
- **Every registered gate runs, whatever any other gate does.** `run_gates`
  (`tools/verify.py`) — the `try`/`except Exception` around `gate.run()` means one broken
  gate cannot hide how much else is broken.
- **A gate reports its tool verbatim.** `run_tools` (`tools/gates/__init__.py`) — the
  failure detail is the tool's own stdout and stderr, never a summary of them.
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

Nothing third-party is **imported**, on purpose. The gates reach their tools by
`subprocess`, through `uv run --group dev`, at the moment the gate runs. So a missing or
broken toolchain surfaces as *that gate* failing with the real error, not as an import
error before any gate runs. `ruff`, `mypy` and `pytest` are declared in the `dev`
dependency group in `pyproject.toml` (DEC-0005 settled that these three are the static
enforcement layer).

`uvx` is not usable and must not be substituted: it builds an isolated environment with no
dev dependencies, so gate 2 reports `pytest` as a missing library stub for every test
module that imports it, and gate 14 would have no `pytest` at all.

`tools/gates/lint.py`, `types.py` and `tests.py` import `GateResult` under
`TYPE_CHECKING` only, and `run_tools` imports it inside the function body: `tools.verify`
imports `tools.gates` to build `REGISTRY`, so a module-level import back would be a cycle.

Tests additionally use `pytest` (dev group) and invoke `make` and the real runner through
`subprocess`.

## Must not depend on
- **Anything under `src/`.** The harness checks the product; a harness importing the thing
  it checks can be broken by the same defect it is meant to catch.
- **Any third-party package at import time.** `python -m tools.verify` must import on a
  clean checkout with nothing installed.
- **Any inference client or model SDK** (I1, I2) — as for every module in this repository.

## Tests
`tools/tests/test_verify.py`, `tools/tests/test_gates_static.py` and
`tools/tests/conftest.py`. Twenty-one tests, 10 unit / 11 integration (48% unit, inside the
40–60% band gate 15 will enforce at T-0007).

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

Integration, through the real `Makefile`, the real runner and the real tools:
- `make verify` over this repository exits 0 and prints the registered count;
- a copy of the harness whose `REGISTRY` is reset to one literal failing `Gate(...)` exits
  non-zero;
- that run names the failing gate and prints `"1 gates registered, 1 failed"`;
- each of the three bad inputs, planted where the tool scans it, makes a real `make verify`
  exit non-zero and print `FAIL  gate <n>` for exactly the gate it targets. Each of those
  copies registers **only the gate it is about** (`conftest.only_gate`), so a proof about
  gate 1 does not also pay for `mypy` and the whole of `pytest` inside the copy. What
  survives the filter is this repository's real registered gate, with its real name, cost
  and `run`, reached through the copied `REGISTRY` itself; nothing any proof asserts
  changed, and `make verify` went from 133 s to 84 s;
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
runner, `ruff`, `mypy`, `pytest` and the bad input are all real. Nine of the twenty-one
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
`15 passed, 6 skipped` where a full run prints `21 passed`. **`make verify` alone is
therefore not evidence that this suite ran in full** — that is why every task also runs
`uv run --group dev pytest tools/tests/ -q` directly, and why one test asserts the suite
reports zero skips when the marker is absent.

Both test modules import the shared pieces as `from tools.tests.conftest import ...`, not
`from conftest import ...`. `tools/` is a package, so `mypy --strict tools/` names that file
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
        9 files already formatted
PASS  gate 2  types
        Success: no issues found in 9 source files
PASS  gate 14  tests
        ======================== 21 passed in 83.42s (0:01:23) =========================
3 gates registered, 0 failed
$ echo $?
0
```

Gate 14 dominates the run because this suite drives the whole harness against copies of it:
nine of the twenty-one tests run a real `make verify` or a real gate over a tree they copied
first. That is its cost 3, and it is the price of proving the gates instead of asserting
them. Each of those copies registers only the gate its proof is about, which is what took
`make verify` from 133 s to 84 s; the copy in the gate 14 proofs still runs a real `pytest`
over itself, and that is the floor.

Each `PASS` carries its tool's own summary line, so a run that checked less than it should
is visible as one (DEC-0024) — gate 14's line is a count, gate 1's `All checks passed!` is
not. One level down, inside a process this suite spawned, the same command reports the
difference:

```
$ env CADGPT_NESTED_VERIFY=1 make verify
python3 -m tools.verify
PASS  gate 1  format-and-lint
        All checks passed!
        9 files already formatted
PASS  gate 2  types
        Success: no issues found in 9 source files
PASS  gate 14  tests
        =================== 15 passed, 6 skipped in 63.06s (0:01:03) ===================
3 gates registered, 0 failed
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
gate 14  cost 3  tests
3 gates registered
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
- Three gates of sixteen are registered. A green `make verify` today means the tree is
  lint-clean, type-clean under `--strict` and its tests pass — and nothing more. In
  particular **nothing about `src/` is checked yet**, because there is no `src/`. Gates
  4–7 are T-0003 to T-0006; `docs/architecture/harness.md` names all sixteen and when each
  becomes real.
- **DEC-0023 is closed**, not open: gate 4 does not close the raw-HTTP path. `ifctester` is a
  forced inherited component and pulls `requests` into the engine closure, so gate 4 asserts
  instead that no inference SDK resolves and that every HTTP-capable package in the closure
  is on an allowlist. The raw-HTTP path is closed by **gate 3** (import contracts), which
  forbids `src/engine` from importing any HTTP client or socket module, and gate 3 ships at
  **C1.1** — it cannot exist before there is an `src/` package to constrain. Until C1.1 that
  path is unguarded, and that is known and scheduled, not overlooked.
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
