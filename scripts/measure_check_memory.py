"""Measure the peak memory a real check actually costs, so `MAX_UPLOAD_BYTES` is derived
rather than guessed (T-0033, `docs/tasks/T-0033-measured-upload-ceiling.md`).

What is measured is **peak RSS of the process doing the work** -- not wall time, and not
container memory at rest. Each model is checked in its own subprocess (`--child`), and
right after `cadgpt_engine.run_check` returns, that subprocess reads its own peak resident
set size from `resource.getrusage(RUSAGE_SELF).ru_maxrss`. On Linux this is a
high-water mark the kernel has tracked since the process started, not a poll -- there is
no window in which a spike between two samples goes unseen, which a `psutil`-polling
approach would have.

Each model gets a fresh subprocess so one model's peak cannot be inflated by a previous
model's allocations still being resident, and so a model large enough to crash the
process (the whole point of this measurement) takes down only that one measurement rather
than the run.

Usage, from the repository root, against the production image so the number means what it
claims about the worker:

    docker run --rm --entrypoint python \\
        -v "$(pwd)/scripts:/scripts:ro" \\
        -v "$(pwd)/packages/engine/tests/fixtures:/fixtures:ro" \\
        -v "/path/to/models:/models:ro" \\
        cadgpt-api:latest /scripts/measure_check_memory.py \\
        --ids /fixtures/door_width.ids \\
        --model "Duplex 2.3MB=/models/Duplex_A_20110907.ifc" \\
        --model "Schependomlaan 47MB=/models/Schependomlaan.ifc" \\
        --model "Schependomlaan_large (generated, 94.4MB)=/models/Schependomlaan_large.ifc"

The third `--model` label names the file honestly: it is the output of
`scripts/generate_large_ifc_model.py`, not a fourth real-world sample, and the label says
so rather than inventing a plausible-sounding name or size for it.
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
from pathlib import Path


def _run_child(ifc_path: Path, ids_path: Path) -> None:
    """Invoked as `--child`: run one check in *this* process and report its own peak RSS.

    Never imports anything from `cadgpt` (the Django service) -- this is the engine's own
    entry point, `run_check`, called exactly as `CheckRunExecutor._evaluate` calls it.
    """
    from cadgpt_engine.check import run_check

    t0 = time.monotonic()
    report = run_check(ifc_path, ids_path)
    elapsed = time.monotonic() - t0
    # ru_maxrss is kilobytes on Linux (it is bytes on macOS -- this script targets the
    # Linux container the worker actually runs in, per the module docstring).
    peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(
        json.dumps(
            {
                "peak_rss_kb": peak_kb,
                "elapsed_seconds": round(elapsed, 2),
                "status": report.status.value,
                "entities_evaluated": report.passed + report.failed + report.indeterminate,
            }
        )
    )


def _measure_one(ifc_path: Path, ids_path: Path, python: str) -> dict[str, object]:
    proc = subprocess.run(  # noqa: S603
        [python, str(Path(__file__).resolve()), "--child", str(ifc_path), str(ids_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr_tail = proc.stderr.strip()[-500:]
        return {
            "peak_rss_kb": None,
            "elapsed_seconds": None,
            "status": f"CHILD FAILED (exit {proc.returncode}): {stderr_tail}",
            "entities_evaluated": None,
        }
    # The child's only stdout line is the JSON payload.
    return dict(json.loads(proc.stdout.strip().splitlines()[-1]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--child",
        nargs=2,
        metavar=("IFC", "IDS"),
        help=argparse.SUPPRESS,  # internal: this invocation IS the measured process
    )
    parser.add_argument(
        "--ids", type=Path, help="the IDS rule set every model is checked against"
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="a model to measure, repeatable",
    )
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)

    if args.child:
        _run_child(Path(args.child[0]), Path(args.child[1]))
        return 0

    if not args.ids or not args.model:
        parser.error("--ids and at least one --model are required")

    rows: list[tuple[str, int, dict[str, object]]] = []
    for spec in args.model:
        label, _, path_str = spec.partition("=")
        path = Path(path_str)
        size_bytes = path.stat().st_size
        print(f"measuring {label} ({size_bytes:,} bytes)...", file=sys.stderr)
        result = _measure_one(path, args.ids, args.python)
        rows.append((label, size_bytes, result))
        print(f"  -> {result}", file=sys.stderr)

    print()
    print("| model | size (MB) | peak RSS (MB) | elapsed (s) | status |")
    print("| --- | ---: | ---: | ---: | --- |")
    for label, size_bytes, result in rows:
        size_mb = size_bytes / (1024 * 1024)
        peak_kb = result["peak_rss_kb"]
        peak_mb = f"{peak_kb / 1024:.1f}" if isinstance(peak_kb, int) else "n/a"
        elapsed = result["elapsed_seconds"]
        elapsed_s = f"{elapsed:.1f}" if isinstance(elapsed, (int, float)) else "n/a"
        print(f"| {label} | {size_mb:.1f} | {peak_mb} | {elapsed_s} | {result['status']} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
