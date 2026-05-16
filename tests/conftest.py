"""Shared test helpers for the Spec Kit test suite.

This conftest is the upstream conftest (vendored verbatim from v0.8.10)
augmented with the repo-root sys.path insertion that the Linear
extension tests require to import ``extensions.linear.scripts.*``.

Constitution P1: do not modify upstream test surface. The only addition
below is the path-bootstrap block at the very top.
"""

from __future__ import annotations

# ---- Linear-fork addition: put repo root on sys.path ---------------------
# Lets ``from extensions.linear.scripts.protocols import …`` resolve
# regardless of where pytest is launched.
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# ---- end Linear-fork addition --------------------------------------------

import os
import re
import shutil
import subprocess

import pytest

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _has_working_bash() -> bool:
    """Check whether a functional native bash is available.

    On Windows, ``subprocess.run(["bash", ...])`` uses CreateProcess,
    which searches System32 *before* PATH — so it may find the WSL
    launcher even when Git-for-Windows bash appears first in PATH via
    ``shutil.which``.  We therefore probe with bare ``"bash"`` (the
    same way test helpers invoke it) to get an accurate result.

    On Windows, only Git-for-Windows bash (MSYS2/MINGW) is accepted.
    The WSL launcher is rejected because it runs in a separate Linux
    filesystem and cannot handle native Windows paths used by the
    test fixtures.

    Set SPECKIT_TEST_BASH=1 to force-enable bash tests regardless.
    """
    if os.environ.get("SPECKIT_TEST_BASH") == "1":
        return True
    if shutil.which("bash") is None:
        return False
    try:
        r = subprocess.run(
            ["bash", "-c", "echo ok"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0 or "ok" not in r.stdout:
            return False
    except (OSError, subprocess.TimeoutExpired):
        return False
    if sys.platform == "win32":
        try:
            u = subprocess.run(
                ["bash", "-c", "uname -s"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            kernel = u.stdout.strip().upper()
            if not any(k in kernel for k in ("MSYS", "MINGW", "CYGWIN")):
                return False
        except (OSError, subprocess.TimeoutExpired):
            return False
    return True


requires_bash = pytest.mark.skipif(
    not _has_working_bash(), reason="working bash not available"
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from Rich-formatted CLI output."""
    return _ANSI_ESCAPE_RE.sub("", text)


# ---------------------------------------------------------------------------
# Auth config isolation — prevents tests from reading ~/.specify/auth.json
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_auth_config(monkeypatch):
    """Ensure no test reads the real ~/.specify/auth.json."""
    from specify_cli.authentication import http as _auth_http

    monkeypatch.setattr(_auth_http, "_config_override", [])
    # Also clear the per-process cache so tests that unset _config_override
    # won't see a previously cached real-file result.
    monkeypatch.setattr(_auth_http, "_config_cache", None)
