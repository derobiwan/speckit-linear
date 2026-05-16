"""T021 contract test: extensions/linear/extension.yml conforms to upstream
ExtensionManifest schema (src/specify_cli/extensions.py).

This is a contract test against the *upstream* schema validator — the Linear
extension is a first-class plugin that must load through ``ExtensionManifest``
exactly like ``extensions/git/`` does. We do not patch the validator; if
upstream changes its rules, the Linear manifest must be updated to keep up
(Constitution P1 — no local changes to upstream surface).

What we verify:
  * The file exists at the expected location
  * ``ExtensionManifest(path)`` constructs without raising
  * No correction warnings (i.e., the manifest is authored in canonical form)
  * Manifest declares all 9 core-command before/after hooks (FR-018,
    Contract C2)
  * Manifest declares ``mcp__linear__`` as a required tool (Constitution P8)
  * Author field is non-empty (Analyze finding A6 remediation)
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = REPO_ROOT / "extensions" / "linear" / "extension.yml"

CORE_COMMANDS = (
    "specify",
    "plan",
    "tasks",
    "clarify",
    "analyze",
    "checklist",
    "implement",
    "constitution",
    "taskstoissues",
)


@pytest.fixture(scope="module")
def manifest():
    if not MANIFEST_PATH.exists():
        pytest.fail(f"Extension manifest missing: {MANIFEST_PATH}. Create it per T022.")
    from specify_cli.extensions import ExtensionManifest

    return ExtensionManifest(MANIFEST_PATH)


class TestManifestLoadsCleanly:
    def test_manifest_file_exists(self):
        assert (
            MANIFEST_PATH.exists()
        ), f"Expected manifest at {MANIFEST_PATH} (relative to repo root)"

    def test_manifest_validates_without_errors(self, manifest):
        # ExtensionManifest.__init__ raises ValidationError on schema failure;
        # reaching the fixture body means it loaded clean.
        assert manifest.id == "linear"

    def test_manifest_has_no_correction_warnings(self, manifest):
        # A canonical manifest does not trigger auto-rewrites. Any warning here
        # means the manifest is using a deprecated alias-form command name or
        # hook ref. Constitution P1 says we author in canonical form.
        assert (
            manifest.warnings == []
        ), f"Manifest emitted correction warnings: {manifest.warnings!r}"


class TestManifestMetadata:
    def test_id_is_linear(self, manifest):
        assert manifest.id == "linear"

    def test_version_is_semver(self, manifest):
        # Must be valid semver X.Y.Z. Specific patch version is bumped per release
        # (FR-011 tag immutability — every catalog resubmission ships a new tag,
        # so this assertion intentionally accepts any X.Y.Z rather than locking
        # to a specific value that would force test edits on every patch bump).
        import re

        assert re.fullmatch(r"\d+\.\d+\.\d+", manifest.version), (
            f"extension.version must be semver X.Y.Z, got: {manifest.version!r}"
        )

    def test_speckit_version_requirement(self, manifest):
        # The Linear extension must require the upstream v0.8.x line we pinned.
        assert manifest.requires_speckit_version.startswith(">=0.8")

    def test_author_is_non_empty(self, manifest):
        # Analyze A6: author must be populated so the catalog can attribute it.
        ext = manifest.data["extension"]
        assert ext.get("author"), "extension.author must be non-empty"


class TestManifestCoreHooks:
    """FR-018 + Contract C2: every core command has before_ and after_ hooks."""

    @pytest.mark.parametrize("command", CORE_COMMANDS)
    def test_has_before_hook(self, manifest, command):
        hooks = manifest.hooks
        key = f"before_{command}"
        assert key in hooks, f"Missing hook: {key}"

    @pytest.mark.parametrize("command", CORE_COMMANDS)
    def test_has_after_hook(self, manifest, command):
        hooks = manifest.hooks
        key = f"after_{command}"
        assert key in hooks, f"Missing hook: {key}"

    def test_each_hook_has_command_ref(self, manifest):
        for hook_name, hook_data in manifest.hooks.items():
            assert hook_data.get(
                "command"
            ), f"Hook '{hook_name}' missing 'command' field"


class TestManifestTooling:
    def test_declares_linear_mcp_tool(self, manifest):
        """Constitution P8: Linear MCP is the only credential boundary.

        The manifest must declare the linear MCP tool so the runtime grants
        the extension permission to call ``mcp__linear__*``.
        """
        tools = manifest.data.get("requires", {}).get("tools", [])
        assert tools, "requires.tools must list mcp__linear__"
        tool_names = {t.get("name") for t in tools if isinstance(t, dict)}
        # Accept either the prefix marker or the explicit fully-qualified tool.
        linear_tool_declared = any(
            name and (name == "mcp__linear__" or name.startswith("mcp__linear__"))
            for name in tool_names
        )
        assert (
            linear_tool_declared
        ), f"requires.tools must declare an mcp__linear__ entry; got {tool_names!r}"

    def test_linear_mcp_tool_is_required(self, manifest):
        tools = manifest.data.get("requires", {}).get("tools", [])
        for entry in tools:
            if isinstance(entry, dict) and (
                entry.get("name") == "mcp__linear__"
                or (entry.get("name") or "").startswith("mcp__linear__")
            ):
                # Linear extension is Linear-first storage — no local fallback,
                # so the MCP tool is non-optional.
                assert (
                    entry.get("required", False) is True
                ), "mcp__linear__ tool must be marked required (Constitution P2)"
                return
        pytest.fail("No mcp__linear__ tool entry found")


class TestManifestCommandsNamespace:
    """Constitution P1 + upstream command-name pattern: commands must follow
    'speckit.linear.<cmd>'. Linear extension may also expose extension-namespaced
    helper commands (e.g., speckit.linear.repair) — these are tested here.
    """

    def test_all_command_names_are_canonical(self, manifest):
        from specify_cli.extensions import EXTENSION_COMMAND_NAME_PATTERN

        for cmd in manifest.commands:
            name = cmd["name"]
            assert EXTENSION_COMMAND_NAME_PATTERN.match(
                name
            ), f"Command '{name}' violates canonical pattern 'speckit.linear.<cmd>'"
