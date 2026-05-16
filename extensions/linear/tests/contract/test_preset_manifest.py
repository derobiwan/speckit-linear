"""T023 contract test: presets/linear/preset.yml conforms to upstream
PresetManifest schema (src/specify_cli/presets.py).

What we verify (in addition to upstream schema validation):
  * One template per core command (FR-014, Contract C3)
  * Each command override declares strategy = 'wrap' (Constitution P6 —
    we wrap upstream templates, not replace, so future upstream additions
    flow through)
  * The override files exist on disk relative to the preset directory
  * Preset metadata: id == 'linear', author non-empty (A6), semver,
    speckit_version constraint matches the upstream line we pin to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
PRESET_DIR = REPO_ROOT / "presets" / "linear"
PRESET_PATH = PRESET_DIR / "preset.yml"

CORE_COMMANDS = (
    "speckit.specify",
    "speckit.plan",
    "speckit.tasks",
    "speckit.clarify",
    "speckit.analyze",
    "speckit.checklist",
    "speckit.implement",
    "speckit.constitution",
    "speckit.taskstoissues",
)


@pytest.fixture(scope="module")
def manifest():
    if not PRESET_PATH.exists():
        pytest.fail(f"Preset manifest missing: {PRESET_PATH}. Create it per T024.")
    from specify_cli.presets import PresetManifest

    return PresetManifest(PRESET_PATH)


@pytest.fixture(scope="module")
def templates_by_name(manifest):
    return {t["name"]: t for t in manifest.templates}


class TestPresetLoadsCleanly:
    def test_preset_file_exists(self):
        assert (
            PRESET_PATH.exists()
        ), f"Expected preset at {PRESET_PATH} (relative to repo root)"

    def test_preset_validates_without_errors(self, manifest):
        assert manifest.id == "linear"


class TestPresetMetadata:
    def test_id_is_linear(self, manifest):
        assert manifest.id == "linear"

    def test_version_is_semver(self, manifest):
        # Must be valid semver X.Y.Z. Specific patch version is bumped per release
        # (FR-011 tag immutability — every catalog resubmission ships a new tag,
        # so this assertion intentionally accepts any X.Y.Z rather than locking
        # to a specific value that would force test edits on every patch bump).
        import re

        assert re.fullmatch(r"\d+\.\d+\.\d+", manifest.version), (
            f"preset.version must be semver X.Y.Z, got: {manifest.version!r}"
        )

    def test_speckit_version_requirement(self, manifest):
        assert manifest.requires_speckit_version.startswith(">=0.8")

    def test_author_is_non_empty(self, manifest):
        # Analyze A6: author attribution for the catalog.
        assert manifest.author, "preset.author must be non-empty"


class TestPresetCoreCommandCoverage:
    """FR-014 + Contract C3: every core command has an override template."""

    @pytest.mark.parametrize("command", CORE_COMMANDS)
    def test_has_override_for_command(self, command, templates_by_name):
        assert (
            command in templates_by_name
        ), f"Preset missing override for core command '{command}'"

    @pytest.mark.parametrize("command", CORE_COMMANDS)
    def test_override_uses_wrap_strategy(self, command, templates_by_name):
        # Constitution P6: wrap (not replace) so upstream improvements to the
        # core templates flow through automatically. We add our Linear-specific
        # before/after blocks via wrap.
        template = templates_by_name[command]
        strategy = template.get("strategy", "replace")
        assert (
            strategy == "wrap"
        ), f"Override for '{command}' should use strategy='wrap', got '{strategy}'"

    @pytest.mark.parametrize("command", CORE_COMMANDS)
    def test_override_file_exists(self, command, templates_by_name):
        template = templates_by_name[command]
        override_path = PRESET_DIR / template["file"]
        assert (
            override_path.exists()
        ), f"Override file for '{command}' missing on disk: {override_path}"

    @pytest.mark.parametrize("command", CORE_COMMANDS)
    def test_override_replaces_correct_template(self, command, templates_by_name):
        # The 'replaces' (or upstream-equivalent) field declares which core
        # template the wrap is applied to. Must match the command name.
        template = templates_by_name[command]
        replaces = template.get("replaces")
        assert replaces == command, (
            f"Template for '{command}' should declare replaces='{command}', "
            f"got {replaces!r}"
        )


class TestPresetCommandsHaveCommandType:
    def test_all_templates_are_command_type(self, manifest):
        for tmpl in manifest.templates:
            assert tmpl["type"] == "command", (
                f"Template {tmpl['name']!r} must be type='command', "
                f"got {tmpl['type']!r}"
            )
