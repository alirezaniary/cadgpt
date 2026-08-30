"""Bad on purpose: a test that fails, which gate 14 must reject (pytest).

Every gate ships with a proof it fails (DEC-0016). This file is that proof's input for
gate 14. Its name matches neither ``test_*.py`` nor ``*_test.py``, so pytest does not
collect it where it rests; ``tools/tests/test_gates_static.py`` copies the whole harness
into the test's own ``tmp_path``, plants this file there under a collected name, and runs
the gate in the copy. Nothing is removed afterwards and nothing needs to be: the copy goes
when ``tmp_path`` does, and this checkout is never written to. It is lint-clean and
type-clean so that only the gate under test rejects it.
"""


def test_the_probe_fails_on_purpose() -> None:
    """Fail, so that gate 14 has something to reject."""
    assert 2 + 2 == 5
