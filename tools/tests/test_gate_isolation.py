"""Gate 4 — that an inference SDK is unresolvable in the engine environment.

Four proofs, in two pairs.

The two **unit** proofs drive `isolation.verdict` over a described closure. They exist
because the case the gate is for — an engine environment that *does* import an inference
SDK — is the one case a repository that passes its own verify cannot build. Splitting the
rule from the resolution is what makes that case reachable at all.

The two **integration** proofs build the real thing. One resolves this repository's real
`engine` group into a real environment and asserts what is and is not importable there;
the other adds `openai` to a **copy's** `engine` group and requires the real `make verify`
to exit non-zero and name gate 4. Nothing is mocked in either: real `uv`, real wheels, a
real interpreter, a real `Makefile`.

Neither integration test carries a nesting marker, and neither belongs in
`conftest.SPAWNS_A_RE_ENTERING_PROCESS`. The copy that runs `make verify` registers gate 4
only (`conftest.only_gate`), and gate 4 runs `uv` and an interpreter — not this suite — so
it cannot re-enter the harness. A test skipped for a reason untrue about it is a proof
silently lost.
"""

from __future__ import annotations

from pathlib import Path

from tools.gates import isolation
from tools.gates.isolation import ALLOWED_HTTP, ENGINE_GROUP, ResolvedEngineEnvironment
from tools.tests.conftest import copied_tree, make_verify, only_gate

RECORDED_CLOSURE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("requests", ("ifctester",)),
    ("urllib3", ("ifctester",)),
    ("flask", ("ifctester",)),
    ("bcf-client", ("ifctester",)),
)
"""The HTTP-capable half of the engine closure, written out rather than derived from
`ALLOWED_HTTP`. A fixture built from the thing it is checking agrees with it by
construction and proves nothing; this one has to be changed by hand when the allowlist is,
which is the point — DEC-0023 makes that a decision record."""


def test_an_inference_sdk_in_the_closure_fails_the_gate_and_names_it() -> None:
    """The whole reason gate 4 exists, on the one closure this repository cannot build."""
    result = isolation.verdict(
        ResolvedEngineEnvironment(
            package_count=52,
            inference_sdks_importable=("openai",),
            http_capable_reached_via=RECORDED_CLOSURE,
        )
    )

    assert not result.ok
    assert "openai" in result.detail
    assert "anthropic" not in result.detail


def test_the_recorded_http_closure_with_no_inference_sdk_passes() -> None:
    """`requests` and its three companions are allowlisted, not forbidden (DEC-0023).

    Their presence must pass, or the gate would be unsatisfiable while `ifctester` is
    inherited — and the detail must still say they are there, because a gate that reports
    nothing about a known HTTP client in the engine closure is hiding it.
    """
    result = isolation.verdict(
        ResolvedEngineEnvironment(
            package_count=51,
            inference_sdks_importable=(),
            http_capable_reached_via=RECORDED_CLOSURE,
        )
    )

    assert result.ok
    for package, reached_via in RECORDED_CLOSURE:
        assert f"{package} via {reached_via[0]}" in result.detail


def test_the_real_engine_environment_has_no_importable_inference_sdk() -> None:
    """Resolve this repository's real `engine` group and look inside the result.

    This is the assertion `docs/ddd/05-import-contracts.md` calls enforcement tier 1: not
    that nobody wrote the import, but that the package is not there to import.
    """
    environment = isolation.resolve()

    assert environment.inference_sdks_importable == ()
    assert environment.package_count > 0
    reached = {
        (package, root)
        for package, roots in environment.http_capable_reached_via
        for root in roots
    }
    assert reached == set(ALLOWED_HTTP)
    assert isolation.verdict(environment).ok


def test_an_inference_sdk_in_the_engine_group_fails_make_verify(tmp_path: Path) -> None:
    """Add `openai` to a copy's `engine` group; the real `make verify` must reject it.

    The copy is edited, never this checkout: `copied_tree` takes the `Makefile`,
    `pyproject.toml`, `uv.lock` and `tools/` into `tmp_path`, and the copy registers gate 4
    alone so the proof pays for one gate rather than all four.
    """
    copy = copied_tree(tmp_path, only_gate(4))
    declaration = copy / "pyproject.toml"
    declared = declaration.read_text(encoding="utf-8")
    with_sdk = declared.replace(
        f"{ENGINE_GROUP} = [\n", f'{ENGINE_GROUP} = [\n    "openai",\n', 1
    )
    assert with_sdk != declared, (
        f"the copy's pyproject.toml has no `{ENGINE_GROUP} = [` to add an inference SDK "
        f"to, so this test would prove nothing"
    )
    declaration.write_text(with_sdk, encoding="utf-8")

    completed = make_verify(copy)

    assert completed.returncode != 0, completed.stdout + completed.stderr
    assert "FAIL  gate 4  isolation-proof" in completed.stdout, completed.stdout
    assert "openai" in completed.stdout, completed.stdout
