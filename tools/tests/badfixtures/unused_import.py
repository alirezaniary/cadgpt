"""Bad on purpose: an unused import, which gate 1 must reject (ruff, F401).

Every gate ships with a proof it fails (DEC-0016). This file is that proof's input for
gate 1. It is excluded from ruff and mypy at rest in ``pyproject.toml`` and its name
matches no pytest collection pattern, so the repository holds a deliberately bad input and
still passes its own ``make verify``. ``tools/tests/test_gates_static.py`` copies it into a
path the tools scan, runs the gate, and removes it again.
"""

import os
