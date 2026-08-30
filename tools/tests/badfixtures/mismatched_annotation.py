"""Bad on purpose: an annotation the value contradicts, which gate 2 must reject (mypy).

Every gate ships with a proof it fails (DEC-0016). This file is that proof's input for
gate 2. It is lint-clean and format-clean so that only the gate under test rejects it; see
``unused_import.py`` in this directory for why a bad input can sit in the tree at rest.
"""


def half_of(value: int) -> int:
    """Halve an integer."""
    return value // 2


answer: str = half_of(84)
