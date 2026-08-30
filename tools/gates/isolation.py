"""Gate 4 — the isolation proof (``docs/architecture/harness.md``).

Gate 3 checks that nobody *wrote* a forbidden import, and ``importlib`` or a plugin entry
point defeats it. This gate checks the forbidden thing is **not installable**: it resolves
the ``engine`` dependency group into a throwaway environment and imports each inference SDK
there. If the package is not in the resolved environment the call cannot be made however it
is spelled, which is what makes I1 a fact rather than a policy (DEC-0004).

Two things are asserted, and DEC-0023 settles why they are not the same assertion:

* **(a)** every name in ``FORBIDDEN_IN_ENGINE`` raises ``ImportError`` in that environment;
* **(b)** every HTTP-capable package in the resolved closure is in ``ALLOWED_HTTP`` *and*
  is reached through the engine dependency recorded beside it.

(b) is a ratchet, not a purity check. ``ifctester`` is a forced inherited component (I3) and
drags ``requests``, ``urllib3``, ``flask`` and ``bcf-client`` into the engine closure. They
cannot be removed without forking it, so their presence is recorded and attributed rather
than forbidden; what the gate guarantees is that the set does not *grow*. A newly
introduced ``httpx``, or a ``requests`` arriving through something other than
``ifctester``, fails the build. The raw-HTTP path itself is closed by gate 3 at C1.1,
not here.

The gate fails closed. Anything that stops the environment being resolved — a missing
``engine`` group, an unreachable index, an unreadable interpreter — is ``ok=False`` carrying
the resolver's own words, never a skip: an isolation proof that could not run has proved
nothing, and a run that says so is the only honest report of it.

``uv`` is invoked without ``--locked`` or ``--frozen``, so a ``pyproject.toml`` that has
drifted from ``uv.lock`` is resolved as written rather than as last locked. That is what
makes an ``openai`` added to the engine group visible to this gate at all, and it is how
``run_tools`` already reaches ``uv run --group dev``.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tools.gates import REPO_ROOT

if TYPE_CHECKING:
    from tools.verify import GateResult

FORBIDDEN_IN_ENGINE: tuple[str, ...] = ("anthropic", "openai")
"""Inference SDKs. Importing one in the engine environment must raise ImportError."""

HTTP_CAPABLE: tuple[str, ...] = (
    "requests",
    "urllib3",
    "httpx",
    "aiohttp",
    "flask",
    "bcf-client",
)
"""Every package we know can open a socket. Presence is not itself a failure — see below."""

ALLOWED_HTTP: tuple[tuple[str, str], ...] = (
    ("requests", "ifctester"),
    ("urllib3", "ifctester"),
    ("flask", "ifctester"),
    ("bcf-client", "ifctester"),
)
"""(package, reached_via) — an HTTP-capable package a forced inherited component drags in,
recorded with the component that forces it (DEC-0023). Adding a pair here is a decision
record. ``reached_via`` is the **declared member of the engine group** the package is
reached through, not its immediate parent: ``urllib3`` arrives under ``requests`` under
``bcf-client``, and what the ratchet is about is which engine dependency is responsible for
the whole path."""

ENGINE_GROUP = "engine"
"""The dependency group in ``pyproject.toml`` that is ``cadgpt-engine`` (DEC-0004)."""

_GROUP_EDGE = f"(group: {ENGINE_GROUP})"
"""How ``uv tree --invert`` marks the edge from the project to a declared group member."""

_TREE_NODE = re.compile(r"^(?P<prefix>[│ ]*(?:[├└]── )?)(?P<name>\S+) v")
"""One node of a ``uv tree`` listing. The prefix is a whole number of four-column
units — four spaces, a continuation bar, or a ``"├── "``/``"└── "`` connector — so its
length is the node's depth times four. A line that does not match is not a node —
``uv``'s own ``Resolved N packages`` banner, the ``(*)`` footnote — and is skipped; a
format this cannot read yields no roots at all, which fails the gate rather than
passing it."""

_IMPORT_PROBE = """
import importlib, json, sys

importable = []
for name in {names!r}:
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            importable.append(name)
    except Exception:
        importable.append(name)
    else:
        importable.append(name)
json.dump(importable, sys.stdout)
"""
"""Run inside the resolved environment. A ``ModuleNotFoundError`` naming the module itself
is the only outcome that counts as absent: a module that fails to import for any other
reason — including a ``ModuleNotFoundError`` about one of *its* dependencies — is installed,
and an isolation proof that read that as absence would be reporting the wrong thing."""


def _canonical(name: str) -> str:
    """A distribution name in its comparable form (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _joined(names: Iterable[str]) -> str:
    """Names in a stable order for a message, or a word saying there were none."""
    listed = ", ".join(sorted(names))
    return listed if listed else "nothing"


@dataclass(frozen=True)
class ResolvedEngineEnvironment:
    """What a real, built engine environment turned out to contain.

    ``inference_sdks_importable`` holds the ``FORBIDDEN_IN_ENGINE`` names that imported
    there — empty is the only acceptable value. ``http_capable_reached_via`` pairs each
    ``HTTP_CAPABLE`` distribution actually installed with the declared engine dependencies
    it is reached through.
    """

    package_count: int
    inference_sdks_importable: tuple[str, ...]
    http_capable_reached_via: tuple[tuple[str, tuple[str, ...]], ...]


def verdict(environment: ResolvedEngineEnvironment) -> GateResult:
    """Judge a resolved environment. The whole of the gate's rule, and nothing else.

    Separated from resolving one so the rule can be proven against a closure this machine
    could not otherwise produce — an engine environment that *does* contain an inference
    SDK is exactly the case the gate exists for and exactly the case a passing repository
    cannot build.
    """
    from tools.verify import GateResult

    recorded: dict[str, set[str]] = {}
    for package, reached_via in ALLOWED_HTTP:
        recorded.setdefault(_canonical(package), set()).add(_canonical(reached_via))

    failures = [
        f"{name} imports in the engine environment. I1 is not a fact there: an inference "
        f"call is reachable however gate 3 is spelled (DEC-0004). Remove it from the "
        f"{ENGINE_GROUP} dependency group and from everything that group resolves."
        for name in environment.inference_sdks_importable
    ]
    for package, roots in environment.http_capable_reached_via:
        allowed = recorded.get(_canonical(package))
        if allowed is None:
            failures.append(
                f"{package} can open a socket, is in the engine closure and is not in "
                f"ALLOWED_HTTP; it is reached via {_joined(roots)}. The closure may not "
                f"grow an HTTP client silently: allowlisting one is a decision record "
                f"(DEC-0023)."
            )
        elif {_canonical(root) for root in roots} != allowed:
            failures.append(
                f"{package} is reached via {_joined(roots)}, but ALLOWED_HTTP records it "
                f"arriving via {_joined(allowed)}. An HTTP-capable package that changed "
                f"path is a decision record (DEC-0023)."
            )
    if failures:
        return GateResult(ok=False, detail="\n".join(failures))

    present = ", ".join(
        f"{package} via {_joined(roots)}"
        for package, roots in environment.http_capable_reached_via
    )
    return GateResult(
        ok=True,
        detail=(
            f"{environment.package_count} packages resolved from the {ENGINE_GROUP} "
            f"group; {', '.join(FORBIDDEN_IN_ENGINE)} raise ImportError there; "
            f"HTTP-capable present: {present if present else 'none'}"
        ),
    )


class _ResolutionFailed(Exception):
    """A step of building the engine environment did not complete.

    Carries what ``uv`` or the interpreter said, unedited, so the gate's detail is the
    resolver's own message rather than a summary of it.
    """


def _run(command: Sequence[str], *, cwd: Path) -> str:
    """Run one command from ``cwd`` and return its stdout, or raise with its own output."""
    completed = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise _ResolutionFailed(
            f"$ {' '.join(command)}\nexited {completed.returncode}\n"
            f"{(completed.stdout + completed.stderr).strip()}"
        )
    return completed.stdout


def _roots_reaching(package: str) -> tuple[str, ...]:
    """The declared ``engine`` group members through which ``package`` enters the closure.

    ``uv tree --invert`` prints the reverse dependencies of one package and terminates each
    chain at the project node, which carries ``(group: engine)``. The node one level above
    such a line is therefore a declared member of the group, and the set of them is what
    ``ALLOWED_HTTP`` records. ``uv`` expands each package once and abbreviates repeats with
    ``(*)``, so every parent edge is printed even where the subtree under it is not.
    """
    listing = _run(
        [
            "uv",
            "tree",
            "--only-group",
            ENGINE_GROUP,
            "--invert",
            "--package",
            package,
        ],
        cwd=REPO_ROOT,
    )
    depth_to_name: dict[int, str] = {}
    roots: set[str] = set()
    for line in listing.splitlines():
        node = _TREE_NODE.match(line)
        if node is None:
            continue
        prefix: str = node.group("prefix")
        depth = len(prefix) // 4
        depth_to_name[depth] = node.group("name")
        if _GROUP_EDGE in line and depth - 1 in depth_to_name:
            roots.add(depth_to_name[depth - 1])
    return tuple(sorted(roots))


def resolve() -> ResolvedEngineEnvironment:
    """Build a throwaway environment from the engine group and report what is in it.

    The environment is a real virtualenv holding the real wheels, discarded when the
    temporary directory goes. Nothing is faked and nothing is reused between runs: the
    proof is that *this* resolution of the engine group cannot import an inference SDK.
    """
    with tempfile.TemporaryDirectory(prefix="cadgpt-engine-") as workspace:
        root = Path(workspace)
        requirements = root / "engine-requirements.txt"
        environment = root / "env"
        _run(
            [
                "uv",
                "export",
                "--only-group",
                ENGINE_GROUP,
                "--no-hashes",
                "--no-emit-project",
                "--format",
                "requirements.txt",
                "--output-file",
                str(requirements),
            ],
            cwd=REPO_ROOT,
        )
        _run(["uv", "venv", str(environment)], cwd=REPO_ROOT)
        # --no-deps because the export *is* the closure: every package the engine group
        # resolves to is already pinned in that file, so re-resolving it would install the
        # same set having asked the index about it again. Installing the exported set
        # exactly is also what the gate then claims to have built — and it is what lets a
        # warm cache satisfy the whole step without touching the network, which matters
        # for a gate that runs inside every child this repository's test suite spawns.
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(environment),
                "--no-deps",
                "--requirements",
                str(requirements),
            ],
            cwd=REPO_ROOT,
        )
        interpreter = environment / "bin" / "python"
        if not interpreter.exists():
            raise _ResolutionFailed(
                f"the resolved engine environment has no interpreter at {interpreter}, "
                f"so nothing can be imported in it and the isolation proof cannot run"
            )
        importable = json.loads(
            _run(
                [str(interpreter), "-c", _IMPORT_PROBE.format(names=FORBIDDEN_IN_ENGINE)],
                cwd=REPO_ROOT,
            )
        )
        listed = json.loads(
            _run(
                ["uv", "pip", "list", "--python", str(environment), "--format", "json"],
                cwd=REPO_ROOT,
            )
        )
    installed = {_canonical(str(entry["name"])) for entry in listed}
    return ResolvedEngineEnvironment(
        package_count=len(installed),
        inference_sdks_importable=tuple(str(name) for name in importable),
        http_capable_reached_via=tuple(
            (package, _roots_reaching(package))
            for package in HTTP_CAPABLE
            if _canonical(package) in installed
        ),
    )


def run() -> GateResult:
    """Gate 4. Resolve the engine group for real, then judge what came back."""
    from tools.verify import GateResult

    try:
        environment = resolve()
    except _ResolutionFailed as failure:
        return GateResult(
            ok=False,
            detail=(
                f"the {ENGINE_GROUP} environment could not be resolved, so this run "
                f"proves nothing about I1:\n{failure}"
            ),
        )
    return verdict(environment)
