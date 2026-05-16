"""FR-012 enforcement: no per-agent shim files in the Linear plugins (T074).

Constitution P3 (Agent Breadth) requires the Linear extension and preset
to be agent-agnostic. Per-agent rendering is upstream's responsibility
(see `src/specify_cli/integrations/<agent>/`). If a contributor
accidentally adds a per-agent file to our Linear plugins, this test fails
fast in CI.

Closes Analyze finding A4.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories under our control that MUST stay agent-agnostic.
SCOPES = (
    REPO_ROOT / "extensions" / "linear",
    REPO_ROOT / "presets" / "linear",
)

# Per-agent directory names that, if present anywhere under SCOPES, indicate
# an accidental agent-specific shim.
FORBIDDEN_DIR_NAMES = {
    ".claude",
    ".codex",
    ".gemini",
    ".opencode",
    ".github",  # only the subset .github/agents/ + .github/prompts/ is forbidden; see below
    "agents",
}

# Files with agent-name suffix (e.g., command.claude.md) are also forbidden.
FORBIDDEN_FILE_SUFFIX_RE = re.compile(
    r"\.(claude|codex|gemini|copilot|opencode|cursor|windsurf|kiro_?cli|"
    r"roo|qwen|kilocode|kimi|junie|iflow|goose|generic|forge|devin|"
    r"codebuddy|bob|auggie|amp|agy|pi|qodercli|shai|tabnine|trae|vibe|"
    r"lingma)\.(md|toml|yml|yaml|json|prompt\.md|agent\.md)$"
)


@pytest.mark.parametrize(
    "scope", SCOPES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_no_forbidden_agent_directories(scope: Path) -> None:
    if not scope.exists():
        pytest.skip(f"{scope} not present yet (will be created by later phases)")
    offenders: list[Path] = []
    for path in scope.rglob("*"):
        if not path.is_dir():
            continue
        rel_parts = path.relative_to(scope).parts
        if not rel_parts:
            continue
        if rel_parts[0] in FORBIDDEN_DIR_NAMES:
            # .github is partially allowed (.github/workflows/) but
            # .github/agents/ and .github/prompts/ are forbidden under our scope.
            if rel_parts[0] == ".github":
                if len(rel_parts) >= 2 and rel_parts[1] in ("agents", "prompts"):
                    offenders.append(path)
            else:
                offenders.append(path)
    assert not offenders, (
        f"FR-012 violation: per-agent directory(ies) under {scope}:\n  "
        + "\n  ".join(str(o.relative_to(REPO_ROOT)) for o in offenders)
    )


@pytest.mark.parametrize(
    "scope", SCOPES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_no_per_agent_filename_suffixes(scope: Path) -> None:
    if not scope.exists():
        pytest.skip(f"{scope} not present yet (will be created by later phases)")
    offenders = [
        p
        for p in scope.rglob("*")
        if p.is_file() and FORBIDDEN_FILE_SUFFIX_RE.search(p.name)
    ]
    assert not offenders, (
        f"FR-012 violation: per-agent filename(s) under {scope}:\n  "
        + "\n  ".join(str(o.relative_to(REPO_ROOT)) for o in offenders)
    )
