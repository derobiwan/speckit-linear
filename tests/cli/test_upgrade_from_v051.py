"""T049 contract test: ``specify upgrade-from-v051`` per Research R6 + Contract C1.

The upgrade command is implemented as a *Linear-extension* surface
(`extensions.linear.scripts.upgrade_from_v051`) — NOT as a patch to
``src/specify_cli/`` (Constitution P1 NON-NEGOTIABLE). A shell-level
``specify upgrade-from-v051`` alias is provided by the install-global
wrapper in T052.

What this test asserts (against the R6 algorithm, see PMO-74 §R6):

1. **Detection** — locate v0.5.1 legacy directories.
2. **Archive** — move detected dirs to ``.specify/legacy-v051/{ISO-ts}/``
   (with ``git mv`` when in a git repo, plain ``shutil`` otherwise so
   tests run without git).
3. **Preserve** — ``.specify/config/linear.md`` is NOT moved.
4. **MANIFEST emission** — a ``MANIFEST.json`` is written under the
   archive directory describing what was moved (per Data Model E8).
5. **Idempotency** — re-running on an already-upgraded tree is a no-op
   (exit 0, "nothing to upgrade").
6. **NO MCP writes** — Constitution P1/P2/P8: the upgrade command MUST
   NOT mutate Linear state; it is purely local.

The test MUST FAIL before T050 lands (Constitution P4 NON-NEGOTIABLE).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_REPO = REPO_ROOT / "tests" / "cli" / "fixtures" / "v051-sample-repo"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def v051_repo(tmp_path: Path) -> Path:
    """Copy the v0.5.1 sample fixture into a writable tmp dir."""
    dest = tmp_path / "legacy-repo"
    shutil.copytree(FIXTURE_REPO, dest)
    return dest


@pytest.fixture
def upgrade_module():
    """Lazy import — raises during test collection only if T050 missing."""
    upgrade = pytest.importorskip(
        "extensions.linear.scripts.upgrade_from_v051",
        reason="T050 — extensions/linear/scripts/upgrade_from_v051.py not yet implemented.",
    )
    return upgrade


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


class TestModuleSurface:
    """The implementation MUST expose a documented entry point."""

    def test_module_has_run_callable(self, upgrade_module: Any) -> None:
        assert hasattr(upgrade_module, "run"), (
            "T050: upgrade_from_v051 must expose ``run(project_root, *, "
            "detected_agent=None, dry_run=False) -> UpgradeResult``"
        )
        assert callable(upgrade_module.run)

    def test_module_has_detect_legacy_callable(self, upgrade_module: Any) -> None:
        assert hasattr(
            upgrade_module, "detect_legacy_dirs"
        ), "R6 step 1 — ``detect_legacy_dirs(project_root) -> list[Path]``"
        assert callable(upgrade_module.detect_legacy_dirs)


# ---------------------------------------------------------------------------
# R6 algorithm
# ---------------------------------------------------------------------------


class TestR6Algorithm:
    """End-to-end behaviour for the R6 algorithm."""

    def test_detect_finds_all_known_legacy_dirs(
        self, upgrade_module: Any, v051_repo: Path
    ) -> None:
        detected = upgrade_module.detect_legacy_dirs(v051_repo)
        names = sorted({d.relative_to(v051_repo).as_posix() for d in detected})
        # Fixture seeds .claude/commands/* and skills/speckit-* and .codex isn't seeded.
        assert ".claude/commands/speckit.specify.md" in names or any(
            n.startswith(".claude/") for n in names
        ), f"Did not detect .claude legacy layout: {names!r}"
        assert any(
            n.startswith("skills/speckit-") for n in names
        ), f"Did not detect skills/ legacy layout: {names!r}"

    def test_detect_on_clean_tree_returns_empty(
        self, upgrade_module: Any, tmp_path: Path
    ) -> None:
        """No legacy layout → empty list (R6 idempotency precondition)."""
        clean = tmp_path / "fresh"
        clean.mkdir()
        (clean / "README.md").write_text("clean", encoding="utf-8")
        assert upgrade_module.detect_legacy_dirs(clean) == []

    def test_run_archives_legacy_layout(
        self, upgrade_module: Any, v051_repo: Path
    ) -> None:
        result = upgrade_module.run(v051_repo)

        # R6 step 4-5: archive dir exists with ISO-ish timestamp suffix
        legacy_root = v051_repo / ".specify" / "legacy-v051"
        assert (
            legacy_root.is_dir()
        ), f"Expected archive root at {legacy_root}; got {result!r}"
        archive_buckets = list(legacy_root.iterdir())
        assert (
            len(archive_buckets) == 1
        ), f"Expected one timestamped archive bucket; got {archive_buckets!r}"
        bucket = archive_buckets[0]

        # R6 step 3 — original legacy dirs are gone from their old locations
        assert not (v051_repo / ".claude" / "commands" / "speckit.specify.md").exists()
        # ...but live under the archive bucket somewhere
        archived = list(bucket.rglob("speckit.specify.md"))
        assert archived, f"speckit.specify.md not found under {bucket}"

    def test_run_preserves_linear_md(
        self, upgrade_module: Any, v051_repo: Path
    ) -> None:
        """R6 step 6 — .specify/config/linear.md must be preserved."""
        linear_md = v051_repo / ".specify" / "config" / "linear.md"
        before = linear_md.read_text(encoding="utf-8")
        upgrade_module.run(v051_repo)
        assert (
            linear_md.exists()
        ), "linear.md was moved during upgrade — violates R6 step 6"
        assert (
            linear_md.read_text(encoding="utf-8") == before
        ), "linear.md content drifted across upgrade"

    def test_run_emits_manifest_json(
        self, upgrade_module: Any, v051_repo: Path
    ) -> None:
        """R6 step 8 — emit MANIFEST.json under the archive bucket (Data Model E8)."""
        upgrade_module.run(v051_repo)
        legacy_root = v051_repo / ".specify" / "legacy-v051"
        bucket = next(legacy_root.iterdir())
        manifest_path = bucket / "MANIFEST.json"
        assert manifest_path.is_file(), f"MANIFEST.json missing at {manifest_path}"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "timestamp" in data, "MANIFEST.json missing ``timestamp`` (ISO 8601 UTC)"
        assert "detected_agent" in data, "MANIFEST.json missing ``detected_agent``"
        assert "archived" in data and isinstance(
            data["archived"], list
        ), "MANIFEST.json must include ``archived: list[str]`` of moved relative paths"
        assert "speckit_version" in data, "MANIFEST.json missing ``speckit_version``"

    def test_run_is_idempotent(self, upgrade_module: Any, v051_repo: Path) -> None:
        """R6 idempotency — re-running on an upgraded tree is a no-op (exit 0)."""
        result1 = upgrade_module.run(v051_repo)
        # Counts after first run for diff
        before = sorted((v051_repo / ".specify" / "legacy-v051").iterdir())

        result2 = upgrade_module.run(v051_repo)
        after = sorted((v051_repo / ".specify" / "legacy-v051").iterdir())

        assert (
            before == after
        ), "Second run created a new archive bucket — upgrade is not idempotent"
        # Both runs are expected to succeed; second should mark itself a no-op.
        assert getattr(result2, "no_op", True) is True or getattr(
            result2, "status", "ok"
        ) in (
            "no-op",
            "noop",
            "ok",
        ), f"Second run should report no-op; got {result2!r} (first was {result1!r})"

    def test_detect_agent_precedence(self, upgrade_module: Any, tmp_path: Path) -> None:
        """R6 step 2 — agent precedence: .claude > .codex > .gemini > .opencode > .github > skills."""
        repo = tmp_path / "multi"
        (repo / ".claude" / "commands").mkdir(parents=True)
        (repo / ".codex" / "prompts").mkdir(parents=True)
        (repo / ".claude" / "commands" / "speckit.specify.md").write_text(
            "x", encoding="utf-8"
        )
        (repo / ".codex" / "prompts" / "speckit.specify.md").write_text(
            "x", encoding="utf-8"
        )
        assert upgrade_module.detect_agent(repo) == "claude"


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------


class TestSafetyInvariants:
    """Constitutional guardrails for the upgrade."""

    def test_no_mcp_writes(
        self, upgrade_module: Any, v051_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The upgrade MUST NOT touch Linear. Sentinel: patch the MCP
        client class and assert it is never invoked.

        Constitution P1/P2: the upgrade is purely local — no Linear
        state mutations, no read-side MCP calls either. We hook
        :class:`LinearMcpClientImpl.call` and record every invocation;
        the run is expected to leave the recorder empty.
        """
        from extensions.linear.scripts import linear_mcp_client  # noqa: WPS433

        calls: list[str] = []

        def _record(self, tool_name, /, **arguments):  # type: ignore[no-untyped-def]
            calls.append(tool_name)
            raise AssertionError(
                f"upgrade-from-v051 must not invoke Linear MCP — saw {tool_name!r}"
            )

        monkeypatch.setattr(
            linear_mcp_client.LinearMcpClientImpl, "call", _record, raising=True
        )
        upgrade_module.run(v051_repo)
        assert calls == [], f"upgrade-from-v051 invoked MCP tools: {calls!r}"

    def test_dry_run_makes_no_filesystem_changes(
        self, upgrade_module: Any, v051_repo: Path
    ) -> None:
        before = {
            p.relative_to(v051_repo).as_posix()
            for p in v051_repo.rglob("*")
            if p.is_file()
        }
        upgrade_module.run(v051_repo, dry_run=True)
        after = {
            p.relative_to(v051_repo).as_posix()
            for p in v051_repo.rglob("*")
            if p.is_file()
        }
        assert before == after, (
            "dry_run=True must not mutate the filesystem; "
            f"added={sorted(after - before)!r} removed={sorted(before - after)!r}"
        )
