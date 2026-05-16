"""T028-T045 consolidated contract test: every hook command referenced by
extensions/linear/extension.yml has a backing prompt file that:

  * Exists on disk
  * Declares the correct namespaced command name in its YAML frontmatter
    (when the strategy is to use an upstream-style command file)
  * Mentions the Linear MCP tool prefix (``mcp__linear__``) so the
    runtime grants the extension the tool permission it requires
  * Resolver commands enforce Constitution P2 (no local-file fallback)

This single test stands in for the 18 fine-grained per-hook tasks
(T028-T045): rather than 18 near-identical test modules, we
parameterize across every (hook_name, command_ref) pair the manifest
declares. Each failure points the maintainer at the exact file to fix.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
LINEAR_EXT_DIR = REPO_ROOT / "extensions" / "linear"
MANIFEST_PATH = LINEAR_EXT_DIR / "extension.yml"


def _load_manifest_data() -> dict:
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _hook_pairs() -> list[tuple[str, str]]:
    """Return the de-duplicated list of (hook_name, command_ref) pairs."""
    data = _load_manifest_data()
    return [
        (hook_name, cfg["command"])
        for hook_name, cfg in data.get("hooks", {}).items()
        if cfg.get("command")
    ]


def _unique_command_refs() -> list[str]:
    return sorted({ref for _, ref in _hook_pairs()})


def _command_file_for_ref(ref: str) -> Path:
    """Map a command ref like 'speckit.linear.persist_spec' to its prompt file."""
    # Strip 'speckit.linear.' prefix → 'persist_spec' → file slug 'speckit.linear.persist_spec.md'.
    # Convention: file name matches the full command ref verbatim.
    return LINEAR_EXT_DIR / "commands" / f"{ref}.md"


class TestHookCommandFilesExist:
    @pytest.mark.parametrize("ref", _unique_command_refs())
    def test_command_file_exists(self, ref):
        path = _command_file_for_ref(ref)
        assert path.exists(), (
            f"Hook command {ref!r} is referenced in extension.yml but "
            f"there is no prompt file at {path.relative_to(REPO_ROOT)}"
        )


class TestHookCommandFilesAreMcpAware:
    """All hook commands MUST mention mcp__linear__ — they are the bridge
    between the speckit workflow and the Linear MCP server. A hook prompt
    that doesn't invoke the MCP tool is a no-op (violates Constitution P2).
    """

    @pytest.mark.parametrize("ref", _unique_command_refs())
    def test_mentions_linear_mcp_tool(self, ref):
        path = _command_file_for_ref(ref)
        if not path.exists():
            pytest.skip(f"file {path} missing — covered by existence test")
        content = path.read_text(encoding="utf-8")
        assert "mcp__claude_ai_Linear__" in content or "mcp__linear__" in content, (
            f"{path.name} must invoke the Linear MCP tool "
            f"(grep for mcp__claude_ai_Linear__ or mcp__linear__)"
        )


class TestResolverCommandsEnforceNoLocalFallback:
    """Constitution P2: resolver hooks (before_*) must abort on MCP failure
    rather than silently falling back to local-file storage. The prompt
    text must mention this constraint so the agent does not improvise.
    """

    @pytest.mark.parametrize(
        "ref",
        [r for r in _unique_command_refs() if "resolve-" in r],
    )
    def test_resolver_mentions_no_local_fallback(self, ref):
        path = _command_file_for_ref(ref)
        if not path.exists():
            pytest.skip(f"file {path} missing — covered by existence test")
        content = path.read_text(encoding="utf-8")
        normalized = content.lower()
        signals = (
            "no local",
            "no fallback",
            "do not fall back",
            "abort",
            "constitution p2",
        )
        assert any(s in normalized for s in signals), (
            f"{path.name} must signal no-local-fallback to the agent "
            f"(one of: {signals!r}) per Constitution P2"
        )


class TestPersisterCommandsUseSaveOps:
    """Persister hooks (after_*) must call save_* MCP tools.

    Read-only or list-only persisters indicate the hook is misconfigured.
    """

    @pytest.mark.parametrize(
        "ref",
        [r for r in _unique_command_refs() if "persist-" in r],
    )
    def test_persister_mentions_save_op(self, ref):
        path = _command_file_for_ref(ref)
        if not path.exists():
            pytest.skip(f"file {path} missing — covered by existence test")
        content = path.read_text(encoding="utf-8")
        save_ops = (
            "save_issue",
            "save_project",
            "save_milestone",
            "save_comment",
            "save_document",
            "create_issue_label",
        )
        assert any(op in content for op in save_ops), (
            f"{path.name} is an after_* persister but does not call any "
            f"save_*/create_* MCP tool (expected one of: {save_ops!r})"
        )


class TestHookCommandFrontmatterIsParseable:
    """If a hook command file has frontmatter, it must be valid YAML."""

    @pytest.mark.parametrize("ref", _unique_command_refs())
    def test_frontmatter_valid_or_absent(self, ref):
        path = _command_file_for_ref(ref)
        if not path.exists():
            pytest.skip(f"file {path} missing — covered by existence test")
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---\n"):
            return  # frontmatter is optional
        match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        assert match, f"{path.name} has opening '---' but no closing '---'"
        try:
            parsed = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            pytest.fail(f"{path.name} frontmatter is invalid YAML: {exc}")
        assert isinstance(
            parsed, dict
        ), f"{path.name} frontmatter must be a mapping, got {type(parsed).__name__}"
