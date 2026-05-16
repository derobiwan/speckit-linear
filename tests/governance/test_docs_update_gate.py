"""T072 — Docs-update pre-commit gate (test-first).

Constitution P9 says: whenever code-affecting paths change, the same
commit must also touch one of the user-facing docs. This test pins the
contract of ``scripts/maintainer/docs_update_gate.py`` BEFORE the
implementation lands.

The gate is a pure stdin/stdout filter so it can be wired into
pre-commit as a ``language: system`` hook with ``pass_filenames: true``
without depending on `git` from inside the hook.

Acceptance (PMO-154):
  * Code change without doc change → fails with a clear message naming
    the relevant doc.
  * Code change *with* doc change → passes.
  * Pure doc change (no code) → passes.
  * Pure vendored-only change → passes (vendored files are P1
    NON-NEGOTIABLE; doc gate skips them, the upstream-sync gate handles
    them).
  * ``[skip-docs]`` in the commit message → passes (audited escape
    hatch).

These tests MUST fail until ``docs_update_gate.py`` lands (P4).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_SCRIPT = REPO_ROOT / "scripts" / "maintainer" / "docs_update_gate.py"


pytestmark = pytest.mark.skipif(
    not GATE_SCRIPT.exists(),
    reason="T072 implementation not yet present — expected during RED phase.",
)


def _run_gate(
    files: list[str], *, commit_msg: str = "test commit"
) -> subprocess.CompletedProcess:
    """Invoke the gate with the given list of staged files."""
    return subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--commit-msg", commit_msg, "--", *files],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


# ---------------------------------------------------------------------------
# Blocking paths
# ---------------------------------------------------------------------------


class TestBlocksCodeChangesWithoutDocUpdate:
    """Code-affecting paths without a doc update MUST fail the gate."""

    @pytest.mark.parametrize(
        "code_path",
        [
            "extensions/linear/scripts/linear_repair.py",
            "extensions/linear/extension.yml",
            "presets/linear/preset.yml",
            "pyproject.toml",
        ],
    )
    def test_code_only_change_is_rejected(self, code_path):
        result = _run_gate([code_path])
        assert result.returncode != 0, (
            f"gate must reject code-only change to {code_path!r}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        # Error message must name at least one allowed doc.
        combined = result.stdout + result.stderr
        assert any(
            doc in combined
            for doc in (
                "README.md",
                "AGENTS.md",
                "CHANGELOG.md",
                "CONTRIBUTING.md",
                "VERSION.md",
            )
        ), f"error must name a doc to update; got {combined!r}"


# ---------------------------------------------------------------------------
# Allow paths
# ---------------------------------------------------------------------------


class TestAllowsCodePlusDocChange:
    """Code-affecting change paired with a doc update MUST pass."""

    @pytest.mark.parametrize(
        "doc_path",
        [
            "README.md",
            "AGENTS.md",
            "CLAUDE.md",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "VERSION.md",
        ],
    )
    def test_code_plus_doc_passes(self, doc_path):
        result = _run_gate(["extensions/linear/scripts/linear_repair.py", doc_path])
        assert (
            result.returncode == 0
        ), f"gate must pass when {doc_path!r} accompanies a code change; stderr={result.stderr!r}"


class TestAllowsDocOnlyChange:
    def test_doc_only_change_passes(self):
        result = _run_gate(["README.md"])
        assert result.returncode == 0

    def test_vendored_only_change_passes(self):
        """Vendored upstream files are owned by upstream — the docs gate
        does not require this fork to update its docs when the vendored
        copy is bumped. The upstream-sync CI gate (T055) covers them.
        """
        result = _run_gate(["src/specify_cli/__init__.py"])
        assert result.returncode == 0

    def test_test_only_change_passes(self):
        """Test additions don't require user-facing doc updates."""
        result = _run_gate(
            ["extensions/linear/tests/contract/test_mcp_calls_linear_repair.py"]
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Escape hatch
# ---------------------------------------------------------------------------


class TestSkipDocsEscapeHatch:
    def test_skip_docs_marker_in_commit_msg_bypasses_gate(self):
        result = _run_gate(
            ["extensions/linear/scripts/linear_repair.py"],
            commit_msg="hotfix: revert bad save_issue payload [skip-docs]",
        )
        assert result.returncode == 0
        # The bypass MUST be audible — script writes a note to stderr.
        assert "skip-docs" in (result.stdout + result.stderr).lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_files_passes(self):
        """An empty stage list is a no-op (pre-commit shouldn't fire with zero files)."""
        result = _run_gate([])
        assert result.returncode == 0

    def test_unrelated_paths_pass(self):
        """Adding LICENSE or top-level config files unrelated to the
        code-affecting set is not gated."""
        result = _run_gate(["LICENSE"])
        assert result.returncode == 0
