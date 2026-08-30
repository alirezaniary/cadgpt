"""Bad on purpose: a test that fails, which gate 14 must reject (pytest).

Every gate ships with a proof it fails (DEC-0016). This file is that proof's input for
gate 14. Its name matches neither ``test_*.py`` nor ``*_test.py``, so pytest does not
collect it where it rests; ``tools/tests/test_gates_static.py`` copies it to a collected
name, runs the gate, and removes it again. It is lint-clean and type-clean so that only
the gate under test rejects it.
"""


def test_the_probe_fails_on_purpose() -> None:
    """Fail, so that gate 14 has something to reject."""
    assert 2 + 2 == 5
