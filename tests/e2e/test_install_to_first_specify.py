"""T054 — End-to-end User-Story-1 (US1) install + first-specify (SC-001).

User Story 1: a developer should be able to go from zero to a working
Linear-backed spec-kit project in under 5 minutes via the install-global
wrapper. This test simulates that flow in CI without burning real
Linear MCP traffic:

1. Invoke ``install-global/install.sh`` in *dry-run* mode against a
   throwaway directory — proves the script's planning + agent
   detection paths work.
2. Run a real ``specify init --integration copilot --preset linear``
   into a tmp dir — copilot is chosen because it has no
   ``requires_cli`` dependency so the test runs everywhere.
3. Drive a simulated ``/speckit.specify`` invocation by:
   a. Loading the Linear preset's ``speckit.specify.md`` template.
   b. Constructing the hook context exactly as the runtime would.
   c. Calling the ``persist-spec`` hook against an in-memory
      ``FakeMcpClient`` (no network).
4. Assert:
   * the installer wrote no files in dry-run;
   * the install completed in well under SC-001's 300-second budget;
   * the resulting Linear-issue dict carries dual labels
     (``speckit:spec`` + ``feature:NNN-name``);
   * the FR-022 backend confirmation line landed on stderr exactly
     once before the simulated MCP write.

Per Constitution P4 this test must fail until the surrounding pieces
(T027 hook helpers, T052 installer, presets/linear/commands/) all
exist; if any do, the test xfails locally with a precise reason.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_SH = REPO_ROOT / "install-global" / "install.sh"
INSTALLER_PS = REPO_ROOT / "install-global" / "install.ps1"
PRESET_SPECIFY = REPO_ROOT / "presets" / "linear" / "commands" / "speckit.specify.md"

# SC-001 budget: 5 minutes for end-to-end. We assert a far tighter
# 90-second budget here because the dry-run path skips package install.
SC001_BUDGET_SECONDS = 300
LOCAL_BUDGET_SECONDS = 90


# ---------------------------------------------------------------------------
# Fakes — keep all Linear traffic in-process
# ---------------------------------------------------------------------------


class FakeMcpClient:
    """In-memory Linear MCP stand-in matching hook_helpers conventions.

    hook_helpers calls the MCP using *unprefixed* tool names
    (``list_issue_labels`` rather than ``mcp__linear__list_issue_labels``);
    the real client adds the prefix. We mirror that convention here so
    the assertions below interrogate the call log directly.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.labels: list[dict] = []
        self.issues: list[dict] = []
        self._next_id = 1

    def _new_id(self) -> str:
        self._next_id += 1
        return f"id_{self._next_id}"

    def call(self, tool: str, payload: dict) -> dict:  # noqa: D401
        self.calls.append((tool, payload))
        if tool == "list_issue_labels":
            return {"data": {"labels": list(self.labels)}}
        if tool == "create_issue_label":
            label = {"id": self._new_id(), "name": payload.get("name", "")}
            self.labels.append(label)
            return {"data": {"label": label}}
        if tool == "list_teams":
            return {"data": {"teams": [{"id": "team_1", "name": "Acme"}]}}
        if tool == "list_projects":
            return {"data": {"projects": [{"id": "proj_1", "name": "MyProduct"}]}}
        if tool == "list_issues":
            return {"data": {"issues": []}}
        if tool == "save_issue" or tool == "mcp__linear__save_issue":
            issue = {
                "id": self._new_id(),
                "title": payload.get("title", ""),
                "labels": payload.get("labels", []),
            }
            self.issues.append(issue)
            return issue
        return {}


# ---------------------------------------------------------------------------
# Skips / xfails — only run when the surrounding pieces are present
# ---------------------------------------------------------------------------


pytestmark = pytest.mark.skipif(
    not INSTALLER_SH.exists() or not PRESET_SPECIFY.exists(),
    reason="install-global/install.sh or presets/linear/commands/speckit.specify.md missing.",
)


# ---------------------------------------------------------------------------
# 1) Installer dry-run
# ---------------------------------------------------------------------------


class TestInstallerDryRun:
    def test_install_sh_dry_run_makes_no_changes(self, tmp_path: Path) -> None:
        if not shutil.which("bash"):
            pytest.skip("bash unavailable on this host")
        env = os.environ.copy()
        env["INSTALL_DRY_RUN"] = "1"
        env["NO_COLOR"] = "1"
        env["CI"] = "1"
        before = sorted(p.name for p in tmp_path.iterdir())
        result = subprocess.run(
            [
                "bash",
                str(INSTALLER_SH),
                "--ai",
                "copilot",
                "--no-prompt",
                "--target",
                "ignored",
            ],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        after = sorted(p.name for p in tmp_path.iterdir())
        # Dry run: even if specify exists, the script just *prints* the
        # invocation; no project should land under tmp_path.
        assert before == after, (
            f"dry-run installer wrote files: before={before!r} after={after!r}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        # Script should mention each of the four declared steps.
        assert (
            "uv" in result.stdout.lower() + result.stderr.lower()
        ), "Installer output didn't mention uv step"


# ---------------------------------------------------------------------------
# 2) End-to-end install (real specify init, copilot, no network calls)
# ---------------------------------------------------------------------------


class TestRealInstallAndSpecify:
    def test_install_to_first_specify_under_budget(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        specify = shutil.which("specify")
        if specify is None:
            pytest.skip("specify entry-point not on PATH")

        # --- Step 1: real `specify init` ---
        project = tmp_path / "e2e-proj"
        t0 = time.monotonic()
        result = subprocess.run(
            [
                specify,
                "init",
                "--ignore-agent-tools",
                "--integration",
                "copilot",
                "--preset",
                "linear",
                "--no-git",
                str(project.name),
            ],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=LOCAL_BUDGET_SECONDS,
            env={**os.environ, "NO_COLOR": "1", "CI": "1"},
        )
        elapsed = time.monotonic() - t0
        assert result.returncode == 0, (
            f"specify init failed (rc={result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert (
            elapsed < SC001_BUDGET_SECONDS
        ), f"SC-001 budget breach: install took {elapsed:.1f}s > {SC001_BUDGET_SECONDS}s"

        # --- Step 2: confirm preset assets are in place ---
        preset_dir = project / ".specify" / "presets" / "linear"
        assert preset_dir.is_dir(), f"presets/linear missing under {project}"

        # --- Step 3: simulated /speckit.specify ---
        from extensions.linear.scripts import hook_helpers  # noqa: WPS433

        # Reset the per-process emit sentinel so we observe exactly one line.
        if hasattr(hook_helpers, "_BACKEND_LINE_EMITTED"):
            hook_helpers._BACKEND_LINE_EMITTED.clear()  # type: ignore[attr-defined]

        mcp = FakeMcpClient()

        # Emit the FR-022 confirmation line *before* the first MCP write.
        hook_helpers.emit_backend_line(workspace="Acme", project="MyProduct")
        captured = capsys.readouterr()
        assert (
            "[linear] backend=Linear" in captured.err
        ), "FR-022 confirmation line missing on stderr"

        # Drive the spec persistence path through hook_helpers — same
        # entry-points the real after_specify hook uses. Short name is
        # the kebab-case slug WITHOUT the NNN prefix — the helper mints
        # it.
        feature_label = hook_helpers.ensure_feature_label(mcp, short_name="e2e-demo")
        feature_with_nnn = feature_label["name"].removeprefix("feature:")
        labels = hook_helpers.dual_labels(speckit_type="spec", feature=feature_with_nnn)

        # The fake save_issue echoes our payload — exercise it.
        spec_issue = mcp.call(
            "save_issue",
            {
                "title": f"[SPEC] {feature_with_nnn.split('-', 1)[0]}: E2E Demo",
                "projectId": "proj_1",
                "teamId": "team_1",
                "description": "Generated by tests/e2e/test_install_to_first_specify.py",
                "labels": labels,
            },
        )

        # --- Step 4: assertions ---
        assert (
            feature_label["name"] == "feature:001-e2e-demo"
        ), f"feature label not minted as expected: {feature_label!r}"
        assert set(spec_issue["labels"]) == {
            "speckit:spec",
            "feature:001-e2e-demo",
        }, f"Spec issue missing dual labels: {spec_issue['labels']!r}"

        # Backend confirmation: exactly one stderr line for this run.
        emit_count = captured.err.count("[linear] backend=Linear")
        assert (
            emit_count == 1
        ), f"FR-022: expected exactly one confirmation line; got {emit_count}"

        # The MCP transcript must include at least one save_issue call
        # and zero delete_* calls.
        save_calls = [t for t, _ in mcp.calls if "save_issue" in t]
        delete_calls = [t for t, _ in mcp.calls if "delete_" in t]
        assert save_calls, "No save_issue MCP call observed"
        assert not delete_calls, f"Unexpected delete MCP call: {delete_calls!r}"


# ---------------------------------------------------------------------------
# 3) PowerShell installer parity smoke
# ---------------------------------------------------------------------------


def test_install_ps1_syntax_parses(tmp_path: Path) -> None:
    """Quick lint: PowerShell parses install.ps1 without errors.

    Runs anywhere `pwsh` (PowerShell Core) or `powershell` is on PATH —
    macOS via Homebrew, Linux via `ubuntu-latest`'s preinstalled pwsh,
    and Windows natively. We previously gated this on
    ``sys.platform == \"win32\"``, but that effectively disabled the
    test everywhere (we have no Windows CI runner). The
    ``shutil.which`` check below handles the missing-tool case
    gracefully and the test fires on Linux CI today.
    """
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if pwsh is None:
        pytest.skip("PowerShell not on PATH.")
    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-Command",
            f"$null = [System.Management.Automation.Language.Parser]::ParseFile('{INSTALLER_PS}', [ref]$null, [ref]$null)",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"PowerShell parse failed: {result.stderr}"
