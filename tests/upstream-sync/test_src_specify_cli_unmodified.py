"""T055 — Upstream-sync diff test (Constitution P1 enforcement / FR-013, FR-014).

This is the CI gate that **fails red** whenever vendored upstream files
diverge semantically from the spec-kit tag pinned in
``.specify/upstream.pin``.

What we diff (FR-013):

* ``src/specify_cli/**``               — upstream CLI surface (strictest)
* ``templates/commands/**``            — upstream command prompts
* ``integrations/**``                  — upstream catalogs
* ``extensions/git/**``                — upstream extension
* ``extensions/selftest/**``           — upstream extension
* ``extensions/template/**``           — upstream extension scaffold
* ``presets/lean/**``                  — upstream preset
* ``presets/scaffold/**``              — upstream preset
* ``presets/self-test/**``             — upstream preset
* ``scripts/bash/**``                  — upstream helper scripts
* ``scripts/powershell/**``            — upstream helper scripts

What we do **not** diff (this fork's contribution):

* ``extensions/linear/**``             — Linear extension (FR-005)
* ``presets/linear/**``                — Linear preset (FR-005)
* ``tests/**``                         — fork-authored test suite

How we diff:

We fetch the upstream commit recorded in ``.specify/upstream.pin``
into a per-session tmp clone (cached across tests in the session) and
do a **whitespace-normalised** byte comparison: trailing whitespace on
each line is stripped and a single terminal newline is enforced. This
matches the standard pre-commit hygiene (``trailing-whitespace`` +
``end-of-file-fixer``) so the gate measures *semantic* drift, not
cosmetic.

Skips are intentional:

* No ``git`` on PATH → skip (cannot fetch upstream).
* Network unreachable → skip (clone fails). CI always has network so
  the gate runs there.
* ``SPECKIT_SKIP_UPSTREAM_SYNC=1`` → skip (developer escape hatch).

The skip behaviour means local pre-commit runs don't flake on
airplanes, but CI's `.github/workflows/upstream-sync.yml` (T056) sets
``SPECKIT_REQUIRE_UPSTREAM_SYNC=1`` which turns skips into failures.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_PIN = REPO_ROOT / ".specify" / "upstream.pin"
UPSTREAM_REPO = "https://github.com/github/spec-kit.git"

# Vendored top-level directories that MUST stay byte-equivalent (modulo
# whitespace normalisation) to the upstream tag.
VENDORED_DIRS: tuple[str, ...] = (
    "src/specify_cli",
    "templates/commands",
    "integrations",
    "extensions/git",
    "extensions/selftest",
    "extensions/template",
    "presets/lean",
    "presets/scaffold",
    "presets/self-test",
    "scripts/bash",
    "scripts/powershell",
)

# Filenames excluded from comparison even within vendored dirs.
# Reason: bundled compiled / cached / IDE artefacts that vary per
# environment.
SKIP_BASENAMES: frozenset[str] = frozenset({"__pycache__", ".DS_Store"})
SKIP_SUFFIXES: tuple[str, ...] = (".pyc", ".pyo")


# ---------------------------------------------------------------------------
# Pinned-upstream helpers
# ---------------------------------------------------------------------------


def _read_pin() -> tuple[str, str | None]:
    """Return ``(tag_or_sha, sha_or_none)`` from ``.specify/upstream.pin``.

    File format is two non-empty lines: the first is a tag (e.g.
    ``v0.8.10``) and the optional second line is the resolved commit
    SHA. Either may be passed as a git ref.
    """
    text = UPSTREAM_PIN.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError(".specify/upstream.pin is empty")
    tag = lines[0]
    sha = lines[1] if len(lines) > 1 else None
    return tag, sha


def _should_skip() -> str | None:
    if os.environ.get("SPECKIT_SKIP_UPSTREAM_SYNC") == "1":
        return "SPECKIT_SKIP_UPSTREAM_SYNC=1 set."
    if shutil.which("git") is None:
        return "git not on PATH; cannot fetch upstream."
    return None


def _require_or_skip(reason: str) -> None:
    if os.environ.get("SPECKIT_REQUIRE_UPSTREAM_SYNC") == "1":
        pytest.fail(f"Upstream-sync gate required but unavailable: {reason}")
    pytest.skip(reason)


@pytest.fixture(scope="session")
def upstream_checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Shallow-clone upstream at the pinned ref into a session tmp dir.

    Cached across all tests in the session — Phase 5's gate runs O(2K)
    file comparisons; we don't want to clone once per test.
    """
    skip_reason = _should_skip()
    if skip_reason is not None:
        _require_or_skip(skip_reason)

    tag, sha = _read_pin()
    ref = sha or tag

    workdir = tmp_path_factory.mktemp("upstream-spec-kit")
    clone_dir = workdir / "spec-kit"

    try:
        # Shallow clone of just the pinned ref. ``--filter=blob:none``
        # would be smaller but is poorly cached on some hosts; we go
        # with ``--depth=1`` against the tag, then check out the SHA.
        subprocess.run(
            ["git", "clone", "--quiet", "--no-tags", UPSTREAM_REPO, str(clone_dir)],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        subprocess.run(
            ["git", "-C", str(clone_dir), "fetch", "--quiet", "origin", ref],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        subprocess.run(
            ["git", "-C", str(clone_dir), "checkout", "--quiet", "--detach", ref],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        _require_or_skip(
            f"Failed to clone upstream {UPSTREAM_REPO}@{ref}: "
            f"rc={exc.returncode} stderr={exc.stderr!r}"
        )
    except subprocess.TimeoutExpired:
        _require_or_skip("git clone of upstream timed out.")

    return clone_dir


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _normalise(content: bytes) -> bytes:
    """Strip trailing whitespace per line + enforce a single final newline.

    Matches pre-commit's ``trailing-whitespace`` + ``end-of-file-fixer``
    behaviour so the test measures semantic, not cosmetic, drift.
    """
    # Normalise line endings to LF first so Windows checkouts compare
    # consistently. We only strip CRs *at* line endings.
    text = content.replace(b"\r\n", b"\n")
    lines = text.split(b"\n")
    cleaned = [ln.rstrip(b" \t") for ln in lines]
    out = b"\n".join(cleaned)
    # Ensure exactly one trailing newline.
    out = out.rstrip(b"\n")
    return out + b"\n" if out else b""


def _walk_files(root: Path) -> Iterable[Path]:
    """Yield every file under ``root`` minus blocked names/suffixes."""
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_BASENAMES for part in path.parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        yield path


# ---------------------------------------------------------------------------
# Test surface
# ---------------------------------------------------------------------------


class TestUpstreamPin:
    """Sanity checks for the pin file itself."""

    def test_pin_file_exists(self) -> None:
        assert (
            UPSTREAM_PIN.is_file()
        ), ".specify/upstream.pin must exist (Phase 1 / T011)."

    def test_pin_file_has_tag(self) -> None:
        tag, _ = _read_pin()
        assert tag.startswith("v"), f"Pin tag must look like 'vX.Y.Z'; got {tag!r}"


class TestVendoredDirsUnchanged:
    """For every vendored dir, every file must match upstream (modulo whitespace)."""

    @pytest.mark.parametrize("rel", VENDORED_DIRS)
    def test_vendored_dir_matches_upstream(
        self, upstream_checkout: Path, rel: str
    ) -> None:
        local_root = REPO_ROOT / rel
        upstream_root = upstream_checkout / rel

        if not upstream_root.exists() and not local_root.exists():
            pytest.skip(
                f"Vendored path {rel!r} does not exist in either tree — "
                "drop it from VENDORED_DIRS once intentional."
            )

        local_files = {
            f.relative_to(local_root).as_posix(): f for f in _walk_files(local_root)
        }
        upstream_files = {
            f.relative_to(upstream_root).as_posix(): f
            for f in _walk_files(upstream_root)
        }

        # Files removed from upstream but still present locally → drift.
        added_locally = sorted(set(local_files) - set(upstream_files))
        assert not added_locally, (
            f"Files added locally under vendored {rel!r} (P1 violation):\n  "
            + "\n  ".join(added_locally)
        )

        # Files present upstream but missing locally → vendor incomplete.
        missing_locally = sorted(set(upstream_files) - set(local_files))
        assert not missing_locally, (
            f"Files missing locally under vendored {rel!r} "
            "(re-run sync-upstream.sh):\n  " + "\n  ".join(missing_locally)
        )

        # Compare contents file-by-file.
        diffs: list[str] = []
        for rel_path, local_path in sorted(local_files.items()):
            upstream_path = upstream_files[rel_path]
            local_norm = _normalise(local_path.read_bytes())
            upstream_norm = _normalise(upstream_path.read_bytes())
            if local_norm != upstream_norm:
                diffs.append(rel_path)

        assert not diffs, (
            f"{len(diffs)} file(s) under {rel!r} drift from upstream "
            "(after whitespace normalisation — P1 violation):\n  "
            + "\n  ".join(diffs)
            + "\n\nFix by either: "
            "(a) reverting the local change, or "
            "(b) filing an upstream PR and bumping .specify/upstream.pin."
        )


class TestLinearDirsExcluded:
    """Make sure we never accidentally diff the Linear contribution."""

    @pytest.mark.parametrize("rel", ["extensions/linear", "presets/linear"])
    def test_linear_dirs_not_in_vendored_set(self, rel: str) -> None:
        assert (
            rel not in VENDORED_DIRS
        ), f"{rel!r} is this fork's contribution and must not be diffed."

    def test_linear_dirs_exist_in_local_tree(self) -> None:
        assert (REPO_ROOT / "extensions" / "linear").is_dir()
        assert (REPO_ROOT / "presets" / "linear").is_dir()
