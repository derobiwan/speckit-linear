"""T070 — Test budget verification (SC-008).

Enforces SC-008: the fork-authored test suite (unit + contract +
integration + perf, *excluding* the 30-agent install smoke matrix
which is parallelized in its own CI job) must finish in under five
minutes on a standard runner.

We can't time *this* run from inside a single test invocation without
recursing, so the gate works in two modes:

  * **Local / CI** (default): assert that the duration recorded by the
    most recent CI run in ``tests/perf/.last-duration-seconds`` is
    under the budget. If the file is absent, the test is skipped with
    an informational reason — the CI workflow writes it on every run.
  * **Self-time** (``SPECKIT_PERF_SELF_TIME=1``): re-invoke pytest as a
    subprocess against the same target set and assert the wall-clock
    is under the budget. Used by the maintainer ahead of a release tag
    (T071).

Keeping these two modes lets CI stay fast (no recursion) while still
letting the maintainer get a single-command "is the suite under
budget?" answer locally before tagging.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DURATION_FILE = REPO_ROOT / "tests" / "perf" / ".last-duration-seconds"
BUDGET_SECONDS = 5 * 60


def test_recorded_duration_under_budget():
    """Read the duration recorded by the most recent CI run.

    The CI workflow appends ``<seconds>\\n`` to
    ``tests/perf/.last-duration-seconds`` after the suite finishes;
    this assertion runs on every PR and fails if a run drifts over
    budget. Skipped locally when the artifact is absent.
    """
    if not DURATION_FILE.exists():
        pytest.skip(
            "No recorded duration — this assertion runs after the CI "
            "writes tests/perf/.last-duration-seconds. Run with "
            "SPECKIT_PERF_SELF_TIME=1 to measure locally."
        )
    raw = DURATION_FILE.read_text(encoding="utf-8").strip().splitlines()
    if not raw:
        pytest.skip("Empty duration file.")
    last = float(raw[-1])
    assert last < BUDGET_SECONDS, (
        f"Test-suite wall-clock {last:.1f}s exceeds SC-008 budget "
        f"({BUDGET_SECONDS}s). Profile slow tests or shard the workflow."
    )


@pytest.mark.skipif(
    os.environ.get("SPECKIT_PERF_SELF_TIME") != "1",
    reason="Self-time mode disabled. Set SPECKIT_PERF_SELF_TIME=1 to enable.",
)
def test_self_timed_run_under_budget(tmp_path: Path) -> None:
    """Re-invoke pytest against the fork-authored suite and assert the
    wall-clock against the SC-008 budget. Skipped unless explicitly
    requested via env var — this test would otherwise infinitely
    recurse during normal runs.
    """
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--quiet",
        # Exclude the 30-agent smoke matrix — that's a separate CI job
        # (`.github/workflows/agent-matrix.yml`) and has its own
        # parallelism budget.
        "--ignore=tests/smoke/test_30_agent_matrix.py",
        # Exclude self to avoid recursion.
        "--ignore=tests/perf/test_suite_duration.py",
    ]
    start = time.monotonic()
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "SPECKIT_PERF_SELF_TIME": "0"},
    )
    duration = time.monotonic() - start

    DURATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DURATION_FILE.open("a", encoding="utf-8") as fh:
        fh.write(f"{duration:.2f}\n")

    assert result.returncode in (0, 5), (
        f"Self-timed pytest returncode={result.returncode}\n"
        f"stdout (last 2KB):\n{result.stdout[-2000:]}\n"
        f"stderr (last 2KB):\n{result.stderr[-2000:]}"
    )
    assert duration < BUDGET_SECONDS, (
        f"Self-timed wall-clock {duration:.1f}s exceeds SC-008 budget "
        f"({BUDGET_SECONDS}s)."
    )
