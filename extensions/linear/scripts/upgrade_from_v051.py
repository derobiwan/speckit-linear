"""T050 — ``specify upgrade-from-v051`` implementation.

This module implements the R6 algorithm from PMO-74 (Research §R6):
detect v0.5.1 legacy directories, archive them under
``.specify/legacy-v051/{ISO-timestamp}/``, preserve
``.specify/config/linear.md``, and emit a MANIFEST.json describing what
was moved.

The command is purposely **not** a patch to ``src/specify_cli/`` —
Constitution P1 (NON-NEGOTIABLE) requires this kind of fork-only
behaviour to live behind the Linear extension. The user-facing
``specify upgrade-from-v051`` alias is provided by the install-global
wrapper (T052). When/if upstream accepts the PR tracked in
``.specify/upstream.notes``, this file becomes the upstream feature.

The module exposes:

* :func:`detect_legacy_dirs` — R6 step 1 (list legacy paths).
* :func:`detect_agent` — R6 step 2 (precedence-based agent inference).
* :func:`run` — orchestrates steps 3-9, returns an :class:`UpgradeResult`.

Constitution invariants enforced here:

* P1 — no patch to upstream surface.
* P2 — local archive only; the module never invokes Linear MCP.
* P8 — credentials are not handled at all (MCP-only boundary is unused).
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

__all__ = [
    "UpgradeResult",
    "detect_agent",
    "detect_legacy_dirs",
    "run",
]


# ---------------------------------------------------------------------------
# Legacy layout catalogue (R6 step 1)
# ---------------------------------------------------------------------------

# Globs are evaluated relative to the project root and capture every
# v0.5.1 emission point we know about. They are intentionally narrow
# (always anchored at the per-agent root) to avoid false positives on
# unrelated ``.claude`` / ``.codex`` directories used by other tooling.
_LEGACY_GLOBS: tuple[tuple[str, str], ...] = (
    # (agent precedence key, glob)
    ("claude", ".claude/commands/speckit.*.md"),
    ("codex", ".codex/prompts/speckit.*.md"),
    ("gemini", ".gemini/commands/speckit.*.toml"),
    ("opencode", ".opencode/command/speckit.*.md"),
    ("github", ".github/agents/speckit.*.agent.md"),
    ("github", ".github/prompts/speckit.*.prompt.md"),
    ("skills", "skills/speckit-*/SKILL.md"),
)

# Agent-precedence order from R6 step 2 (highest first).
_AGENT_PRECEDENCE: tuple[str, ...] = (
    "claude",
    "codex",
    "gemini",
    "opencode",
    "github",
    "skills",
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UpgradeResult:
    """Return shape of :func:`run`.

    Attributes:
        status: ``"ok"`` (archived), ``"no-op"`` (nothing to upgrade), or
            ``"dry-run"`` (would-have-archived list available below).
        no_op: convenience boolean — ``True`` if the upgrade made no
            filesystem changes.
        detected_agent: precedence-based agent name (``None`` when no
            legacy layout was found).
        archive_dir: path of the timestamped archive bucket; ``None`` on
            no-op or dry-run.
        archived: relative paths (POSIX-style) that were moved.
        manifest_path: path of the emitted MANIFEST.json; ``None`` on
            no-op or dry-run.
        timestamp: ISO 8601 UTC timestamp used for the archive bucket
            name (with ``:`` replaced by ``-`` for cross-platform safety).
    """

    status: str
    no_op: bool
    detected_agent: str | None = None
    archive_dir: Path | None = None
    archived: list[str] = field(default_factory=list)
    manifest_path: Path | None = None
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# Detection — R6 steps 1 & 2
# ---------------------------------------------------------------------------


def detect_legacy_dirs(project_root: Path) -> list[Path]:
    """Return every concrete legacy file found under ``project_root``.

    R6 step 1: walk each known glob; return only paths that resolve to
    real files (no symlinks-to-nothing, no directories). The returned
    list is deterministic (sorted by relative path) so callers can rely
    on stable archive ordering.
    """
    project_root = Path(project_root).resolve()
    hits: set[Path] = set()
    for _, glob in _LEGACY_GLOBS:
        for match in project_root.glob(glob):
            if match.is_file():
                hits.add(match)
    return sorted(hits)


def detect_agent(project_root: Path) -> str | None:
    """Return the highest-precedence agent that has legacy artefacts.

    R6 step 2 — precedence order: claude > codex > gemini > opencode >
    github > skills. Returns ``None`` when no legacy layout exists.
    """
    project_root = Path(project_root).resolve()
    present: set[str] = set()
    for agent_key, glob in _LEGACY_GLOBS:
        # Any single hit qualifies — we don't need to enumerate them all.
        if any(p.is_file() for p in project_root.glob(glob)):
            present.add(agent_key)
    for agent in _AGENT_PRECEDENCE:
        if agent in present:
            return agent
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run(
    project_root: Path,
    *,
    dry_run: bool = False,
    speckit_version: str = "1.0.0",
) -> UpgradeResult:
    """Execute the R6 upgrade algorithm.

    Args:
        project_root: path to the project being upgraded.
        dry_run: when True, only report what would happen — no
            filesystem mutations.
        speckit_version: tag recorded in MANIFEST.json. Defaults to
            ``"1.0.0"`` (this release). Tests override.

    Returns:
        :class:`UpgradeResult` describing the outcome.
    """
    project_root = Path(project_root).resolve()
    legacy_files = detect_legacy_dirs(project_root)
    detected_agent = detect_agent(project_root)

    if not legacy_files:
        return UpgradeResult(status="no-op", no_op=True)

    # R6 step 3 — generate timestamp (colons replaced for Windows / shell safety).
    now = _dt.datetime.now(tz=_dt.timezone.utc).replace(microsecond=0)
    timestamp = now.isoformat().replace(":", "-").replace("+00-00", "Z")

    archive_root = project_root / ".specify" / "legacy-v051" / timestamp
    archived_rel: list[str] = []

    if dry_run:
        # Report only — never touch the filesystem.
        for src in legacy_files:
            archived_rel.append(src.relative_to(project_root).as_posix())
        return UpgradeResult(
            status="dry-run",
            no_op=True,
            detected_agent=detected_agent,
            archive_dir=None,
            archived=sorted(archived_rel),
            manifest_path=None,
            timestamp=timestamp,
        )

    archive_root.mkdir(parents=True, exist_ok=True)
    in_git_repo = _is_git_repo(project_root)

    # R6 steps 4-5: move each legacy file under archive_root, preserving relative path.
    for src in legacy_files:
        rel = src.relative_to(project_root)
        dest = archive_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        _move(src, dest, use_git=in_git_repo, project_root=project_root)
        archived_rel.append(rel.as_posix())

    # R6 step 6: clean up now-empty legacy parent directories so the
    # workspace looks tidy. We never delete .specify/config/linear.md
    # because it's outside the legacy glob set by design.
    _prune_empty_legacy_dirs(project_root, archived_rel)

    # R6 step 8: emit MANIFEST.json describing what we did (Data Model E8).
    manifest = {
        "schema_version": "1.0",
        "timestamp": now.isoformat().replace("+00:00", "Z"),
        "detected_agent": detected_agent,
        "speckit_version": speckit_version,
        "archived": sorted(archived_rel),
        "archive_root": archive_root.relative_to(project_root).as_posix(),
        "notes": (
            "Generated by extensions.linear.scripts.upgrade_from_v051. "
            "Restore with `git mv .specify/legacy-v051/<ts>/* .` (see CONTRIBUTING.md)."
        ),
    }
    manifest_path = archive_root / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return UpgradeResult(
        status="ok",
        no_op=False,
        detected_agent=detected_agent,
        archive_dir=archive_root,
        archived=sorted(archived_rel),
        manifest_path=manifest_path,
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _is_git_repo(path: Path) -> bool:
    if shutil.which("git") is None:
        return False
    try:
        r = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def _move(src: Path, dest: Path, *, use_git: bool, project_root: Path) -> None:
    """Move ``src`` → ``dest``. Prefer ``git mv`` for blame continuity."""
    if use_git:
        rel_src = src.relative_to(project_root)
        rel_dest = dest.relative_to(project_root)
        try:
            r = subprocess.run(
                ["git", "-C", str(project_root), "mv", str(rel_src), str(rel_dest)],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            r = None
        if r is not None and r.returncode == 0:
            return
        # git mv failed (file not tracked, conflict, etc.) — fall through to shutil.
    shutil.move(str(src), str(dest))


def _prune_empty_legacy_dirs(project_root: Path, archived_rel: Iterable[str]) -> None:
    """Remove empty parent directories of archived files (best-effort).

    Walks each archived path's parent chain up to the project root and
    removes any directory that became empty. Never traverses outside the
    project root, never removes ``.specify/``.
    """
    protected = {project_root, project_root / ".specify"}
    for rel in archived_rel:
        parent = (project_root / rel).parent
        while (
            parent.exists()
            and parent not in protected
            and parent.is_relative_to(project_root)
        ):
            try:
                if any(parent.iterdir()):
                    break
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
