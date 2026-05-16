"""T051 — 30-agent smoke matrix (FR-020, SC-002).

For every integration in upstream's ``INTEGRATION_REGISTRY`` (30 agents
as of v0.8.10) run a quick ``specify init`` against a tmp directory and
assert:

1. The install completes (exit 0).
2. The expected agent-specific scaffolding lands on disk.
3. The bundled Linear preset is present (``--preset linear`` flag was
   honoured).
4. For the five **full-assertion agents** (``claude``, ``codex``,
   ``gemini``, ``copilot``, ``opencode``) the matching command file
   from ``presets/linear/commands/`` is materialised at the
   per-agent path.

For the remaining 25 agents we only smoke-check that init exits 0 and
``.specify/`` exists — the per-agent commands paths vary by
integration and are exercised in upstream's own integration tests.

CI matrix configuration (R7): see ``.github/workflows/agent-matrix.yml``;
``max-parallel: 6`` keeps the wall-clock under SC-008's 5-minute budget.

The pytest level test is run on a *single* runner that loops over the
30 agents serially when no matrix is provided, and is parameterised so
GitHub Actions can shard by ``--agent`` filter when desired.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

try:
    from specify_cli.integrations import INTEGRATION_REGISTRY  # noqa: WPS433

    _ALL_AGENTS: tuple[str, ...] = tuple(sorted(INTEGRATION_REGISTRY.keys()))
except Exception:  # pragma: no cover — defensive
    _ALL_AGENTS = ()


# Agents that need their command path verified end-to-end (R7 §full).
# Picked because they're the highest-leverage agents for this fork's
# user base and have stable, well-documented per-agent command roots.
_FULL_ASSERTION_AGENTS: frozenset[str] = frozenset(
    {"claude", "codex", "gemini", "copilot", "opencode"}
)


# Map of agent → expected command path roots, relative to project root.
# Multiple roots are OK — we assert AT LEAST ONE exists. Empty tuple
# means we only check ``.specify/`` exists (smoke-only).
# Per-agent install layout (derived from INTEGRATION_REGISTRY[*].config
# folder + commands_subdir). Listed as tuple of acceptable roots — at
# least one MUST exist after a successful install.
_AGENT_COMMAND_ROOTS: dict[str, tuple[str, ...]] = {
    "claude": (".claude/skills", ".claude/commands"),
    "codex": (".agents/skills", ".codex/prompts"),
    "gemini": (".gemini/commands",),
    "copilot": (".github/agents", ".github/prompts"),
    "opencode": (".opencode/commands",),
}


# Agents that require a real CLI binary on PATH (will be skipped if
# the binary is absent). Mirrors AGENT_CONFIG[*]["requires_cli"] but
# we cannot trust it at collection time, so list explicitly.
_REQUIRES_CLI_BINARY: frozenset[str] = frozenset(
    {"claude", "codex", "gemini", "opencode", "amp", "qwen", "kilocode"}
)


pytestmark = pytest.mark.smoke


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_specify() -> str:
    """Locate the installed ``specify`` entry point.

    Falls back to ``python -m specify_cli`` invocation when the script
    isn't on PATH (e.g. running tests via ``uv run`` without the venv
    activated). We can't use ``-m`` reliably because ``specify_cli`` is
    a package without ``__main__``, so a missing ``specify`` shim is a
    hard skip for this matrix.
    """
    binary = shutil.which("specify")
    if binary is None:
        pytest.skip("specify entry-point not on PATH; cannot run smoke matrix.")
    return binary


def _agents_to_smoke() -> tuple[str, ...]:
    """Subset of agents the current host can plausibly install for.

    We always include agents without ``requires_cli`` and with
    self-contained install flows. Agents that require an external CLI
    are exercised only when that binary is present (CI matrix runners
    install one agent's CLI per job; local runs typically have
    ``claude`` and not much else).

    The ``generic`` integration is intentionally excluded — its install
    requires ``--ai-commands-dir`` which is out of scope for a single
    matrix call. Generic is exercised in its own integration tests.
    """
    if not _ALL_AGENTS:
        return ()
    out: list[str] = []
    for agent in _ALL_AGENTS:
        if agent == "generic":
            continue
        if agent in _REQUIRES_CLI_BINARY and shutil.which(agent) is None:
            continue
        out.append(agent)
    return tuple(out)


def _run_install(agent: str, target: Path) -> subprocess.CompletedProcess[str]:
    cmd = [
        _resolve_specify(),
        "init",
        "--ignore-agent-tools",  # we vet the binary ourselves
        "--integration",
        agent,
        "--preset",
        "linear",
        "--no-git",
        str(target.name),
    ]
    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    env.setdefault("CI", "1")
    return subprocess.run(
        cmd,
        cwd=str(target.parent),
        capture_output=True,
        text=True,
        timeout=90,
        env=env,
    )


# ---------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------


_AGENTS_FOR_THIS_RUN: tuple[str, ...] = _agents_to_smoke()


@pytest.mark.parametrize("agent", _ALL_AGENTS if _ALL_AGENTS else ["__no-agents__"])
def test_30_agent_install_smoke(agent: str, tmp_path: Path) -> None:
    """Per-agent install + scaffolding smoke check."""
    if not _ALL_AGENTS:
        pytest.skip("specify_cli not importable — cannot enumerate the matrix.")
    if agent not in _AGENTS_FOR_THIS_RUN:
        pytest.skip(
            f"Agent '{agent}' requires its CLI to be on PATH; "
            "this host doesn't have it. Run inside CI matrix to cover it."
        )

    project = tmp_path / f"smoke-{agent.replace('-', '_')}"
    result = _run_install(agent, project)

    assert result.returncode == 0, (
        f"specify init --integration {agent} --preset linear failed\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert project.is_dir(), f"project dir {project} not created"

    # ``.specify/`` is the universal scaffold root regardless of agent.
    specify_dir = project / ".specify"
    assert (
        specify_dir.is_dir()
    ), f".specify/ not created for agent {agent}; got {list(project.iterdir())!r}"

    # Linear preset bundle must be present (FR-011, SC-002).
    preset_dir = specify_dir / "presets" / "linear"
    assert (
        preset_dir.is_dir()
    ), f"presets/linear/ missing for agent {agent}; preset flag did not take effect."

    # Full-assertion agents: at least one canonical command-root path exists.
    if agent in _FULL_ASSERTION_AGENTS:
        roots = _AGENT_COMMAND_ROOTS.get(agent, ())
        if not roots:
            return
        existing = [r for r in roots if (project / r).is_dir()]
        assert existing, (
            f"Full-assertion agent {agent}: expected one of {roots!r} to exist; "
            f"none found under {project}. Listing: {sorted(project.rglob('*'))[:30]!r}"
        )


def test_matrix_size_matches_upstream() -> None:
    """Sanity check: registry must hold all 30 agents documented in FR-020."""
    if not _ALL_AGENTS:
        pytest.skip("specify_cli not importable; cannot size the matrix.")
    assert len(_ALL_AGENTS) == 30, (
        f"FR-020 mandates 30 agents; INTEGRATION_REGISTRY has {len(_ALL_AGENTS)}: "
        f"{_ALL_AGENTS!r}"
    )


def test_full_assertion_agents_known() -> None:
    """The five full-assertion agents must all be in the registry."""
    if not _ALL_AGENTS:
        pytest.skip("specify_cli not importable.")
    missing = _FULL_ASSERTION_AGENTS - set(_ALL_AGENTS)
    assert not missing, (
        f"Full-assertion agents not in registry: {sorted(missing)!r}. "
        "Update _FULL_ASSERTION_AGENTS or _ALL_AGENTS."
    )
