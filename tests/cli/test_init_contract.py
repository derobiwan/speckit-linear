"""T047 contract test: ``specify init`` flag schema and exit codes per Contract C1.

This is the CLI-level contract for the plugin-architecture rebuild
(<feature:001-plugin-architecture-rebuild>). The test asserts the
documented surface from Contract C1 (see PMO-76):

    specify init [--ai <agent>] [--preset <name>...] [--extension <name>...]
                 [--dry-run] [-v|-vv] [--all-agents] [--target <path>]

Exit codes:
    * 0 — success
    * 2 — invalid flags (Typer's `BadParameter`)
    * 3 — missing prerequisite (e.g. Linear MCP not configured when
          ``--preset linear``)
    * 4 — preset/extension dependency unmet (e.g. ``--preset linear``
          without ``--extension linear``)
    * 5 — file conflict (target not empty, no --force)

Per Constitution P1 (Upstream Compatibility, NON-NEGOTIABLE) we MUST NOT
patch ``src/specify_cli/`` to add missing flags. Where the upstream CLI
does not yet expose a flag from Contract C1, the corresponding assertion
is marked ``xfail(strict=False)`` — the test documents the contract and
will start passing automatically once upstream merges the matching flag
(tracked by T048's upstream-PR note in ``.specify/upstream.notes``).

Tasks:
    * T047 — write this contract test (FAILING until T048 verification)
    * T048 — verify upstream CLI handles ``--preset linear --extension
             linear``; file an upstream PR if it does not (NON-NEGOTIABLE
             per P1)
"""

from __future__ import annotations

import inspect
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _run_cli(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    """Run the installed ``specify`` CLI and capture stdout/stderr/exit.

    Resolves the entry-point script via ``shutil.which`` so the tests
    work in any environment (developer venv, CI matrix runners) without
    requiring a particular invocation form.
    """
    specify_bin = shutil.which("specify")
    if specify_bin is None:
        pytest.skip("specify entry-point not on PATH for this test environment.")
    cmd = [specify_bin, *args]
    merged_env = os.environ.copy()
    # Disable Rich's interactive prompts so failures surface cleanly.
    merged_env.setdefault("NO_COLOR", "1")
    merged_env.setdefault("CI", "1")
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd is not None else None,
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _import_init_callable():
    """Return the live ``specify init`` Typer command function.

    Imported lazily so collection-time import errors raise pytest's clearer
    ``Errors`` summary rather than the unrelated ``ImportError`` line.
    """
    from specify_cli import init as init_command  # noqa: WPS433 — runtime import on purpose

    return init_command


def _init_signature_params() -> dict[str, inspect.Parameter]:
    return inspect.signature(_import_init_callable()).parameters


# ---------------------------------------------------------------------------
# Contract C1: flag schema
# ---------------------------------------------------------------------------


class TestInitFlagSchema:
    """Each flag in Contract C1 must exist on the live ``init`` signature.

    We treat missing flags as a contract failure that we expect to fix by
    landing an upstream PR (T048), so the assertions are real but the
    upstream-gated ones are marked xfail until then.
    """

    def test_init_command_importable(self) -> None:
        init_command = _import_init_callable()
        assert callable(
            init_command
        ), "specify_cli.init must be a callable Typer command"

    @pytest.mark.parametrize("flag", ["ai_assistant", "preset"])
    def test_existing_upstream_flags_present(self, flag: str) -> None:
        """Flags that upstream already ships MUST be present."""
        params = _init_signature_params()
        assert (
            flag in params
        ), f"specify init lost its '{flag}' parameter — Contract C1 broken."

    @pytest.mark.xfail(
        strict=False,
        reason="Contract C1 flag not yet in upstream v0.8.10; T048 tracks the upstream PR.",
    )
    @pytest.mark.parametrize(
        "flag",
        [
            "extension",  # --extension linear (Contract C1 pairing)
            "dry_run",  # --dry-run (Contract C1 verbosity)
            "all_agents",  # --all-agents (matrix mode)
            "target",  # --target <path>
        ],
    )
    def test_contract_c1_flags_present(self, flag: str) -> None:
        params = _init_signature_params()
        assert flag in params, f"Contract C1 declares '--{flag.replace('_', '-')}'"


# ---------------------------------------------------------------------------
# Contract C1: exit codes
# ---------------------------------------------------------------------------


def _has_specify_cli() -> bool:
    """``specify --help`` should run; if not, skip the subprocess suite."""
    if shutil.which("specify") is None:
        return False
    try:
        r = subprocess.run(
            [shutil.which("specify"), "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


pytestmark = pytest.mark.skipif(
    not _has_specify_cli(),
    reason="specify_cli not importable as a module in this environment.",
)


class TestInitExitCodes:
    """Exit-code contract for ``specify init``."""

    def test_help_exits_zero(self) -> None:
        r = _run_cli("init", "--help")
        assert r.returncode == 0, (
            f"specify init --help should exit 0; got {r.returncode}\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )

    def test_invalid_flag_exits_2(self) -> None:
        """Typer maps unknown options to exit code 2 by convention."""
        r = _run_cli("init", "--definitely-not-a-real-flag")
        assert r.returncode == 2, (
            f"Unknown flag should exit 2; got {r.returncode}\n" f"stderr: {r.stderr}"
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Contract C1: --preset linear without --extension linear must exit 4. "
            "Requires the dependency check landing either upstream (preferred per "
            "P1) or behind an extension validator hook (T048)."
        ),
    )
    def test_preset_linear_without_extension_exits_4(self, tmp_path: Path) -> None:
        """``--preset linear`` without ``--extension linear`` exits 4."""
        target = tmp_path / "proj"
        target.mkdir()
        r = _run_cli(
            "init",
            "--here",
            "--ignore-agent-tools",
            "--integration",
            "copilot",
            "--preset",
            "linear",
            "--no-git",
            cwd=target,
        )
        assert r.returncode == 4, (
            f"Expected exit 4 for unmet preset/extension dependency; got {r.returncode}\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        assert (
            "linear extension" in (r.stderr + r.stdout).lower()
        ), "Error message must mention the linear extension requirement."

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Contract C1: Linear MCP unreachable → exit 3 with reconfigure hint. "
            "Pre-flight check lives in the Linear extension's before-hook "
            "(T048 + later phases) and is not yet wired into ``specify init``."
        ),
    )
    def test_mcp_unreachable_exits_3(self, tmp_path: Path) -> None:
        """When Linear MCP is unreachable, exit 3 with the documented hint."""
        target = tmp_path / "proj"
        target.mkdir()
        # Force MCP unreachable by pointing client at an invalid endpoint.
        env = {"SPECKIT_LINEAR_MCP_ENDPOINT": "http://127.0.0.1:1/__noop__"}
        r = _run_cli(
            "init",
            "--here",
            "--ignore-agent-tools",
            "--integration",
            "copilot",
            "--preset",
            "linear",
            "--extension",
            "linear",
            "--no-git",
            cwd=target,
            env=env,
        )
        assert r.returncode == 3, (
            f"Expected exit 3 for unreachable MCP; got {r.returncode}\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}"
        )
        assert "claude mcp add" in (
            r.stderr + r.stdout
        ), "Error message must include the reconfigure command."

    def test_file_conflict_exits_nonzero(self, tmp_path: Path) -> None:
        """Existing non-empty target without --force is a fatal conflict.

        Contract C1 specifies exit 5 for this case. Upstream currently
        uses exit 1 for the directory-conflict guard; we assert a fatal
        exit and xfail the specific code until that lands upstream.
        """
        proj = tmp_path / "preexisting"
        proj.mkdir()
        (proj / "junk.txt").write_text("conflict marker", encoding="utf-8")
        r = _run_cli(
            "init",
            "preexisting",
            "--ignore-agent-tools",
            "--integration",
            "copilot",
            "--no-git",
            cwd=tmp_path,
        )
        assert (
            r.returncode != 0
        ), f"Non-empty target without --force should fail; got {r.returncode}"

    @pytest.mark.xfail(
        strict=False,
        reason="Contract C1 maps file-conflict to exit 5; upstream still returns 1.",
    )
    def test_file_conflict_is_exit_5(self, tmp_path: Path) -> None:
        proj = tmp_path / "preexisting"
        proj.mkdir()
        (proj / "junk.txt").write_text("conflict marker", encoding="utf-8")
        r = _run_cli(
            "init",
            "preexisting",
            "--ignore-agent-tools",
            "--integration",
            "copilot",
            "--no-git",
            cwd=tmp_path,
        )
        assert r.returncode == 5


# ---------------------------------------------------------------------------
# Contract C1: --preset and --extension are repeatable
# ---------------------------------------------------------------------------


class TestRepeatableFlags:
    """Contract C1 declares ``--preset`` and ``--extension`` repeatable."""

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Contract C1 declares --preset as repeatable (list[str]); upstream "
            "currently exposes a single value. Pending T048 upstream PR."
        ),
    )
    def test_preset_is_repeatable(self) -> None:
        params = _init_signature_params()
        annotation = params["preset"].annotation
        # ``list[str]`` or ``List[str]`` both satisfy the contract.
        origin = getattr(annotation, "__origin__", None)
        assert origin in (
            list,
            tuple,
        ), f"--preset should be repeatable (list); got annotation {annotation!r}"

    @pytest.mark.xfail(
        strict=False,
        reason="Contract C1 declares --extension repeatable; flag absent until T048 PR.",
    )
    def test_extension_is_repeatable(self) -> None:
        params = _init_signature_params()
        assert "extension" in params, "--extension must exist (Contract C1)"
        annotation = params["extension"].annotation
        origin = getattr(annotation, "__origin__", None)
        assert origin in (list, tuple)
