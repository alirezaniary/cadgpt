"""``cadgpt-engine`` — the checking engine. No inference dependency, ever (I1 tier 1).

This package is the container for the engine's bounded contexts
(``docs/architecture/module-map.md``): ``ingest``, ``observation``, ``derivation``,
``packs``, ``resolution``, ``evaluation`` and ``findings``. It exports nothing itself —
each context is the public surface for its own contract, documented in its own
``readme.ai.md``.
"""

from __future__ import annotations

__all__: list[str] = []
