"""T072 — Docs-update pre-commit gate (Constitution P9).

Wired into ``.pre-commit-config.yaml`` as a ``language: system`` hook
with ``pass_filenames: true``. Receives every staged file as a CLI
positional argument and the commit message via ``--commit-msg``.

Algorithm:

  1. Bucket the staged files into ``code_paths`` (paths under
     code-affecting roots) and ``doc_paths`` (the canonical set of
     user-facing docs).
  2. Drop vendored upstream paths from the ``code_paths`` set — those
     are owned by upstream and gated by the upstream-sync CI (T055),
     not by P9.
  3. If ``code_paths`` is non-empty AND ``doc_paths`` is empty AND the
     commit message does not contain ``[skip-docs]``, FAIL with a
     clear message naming the docs that should be touched.

Exit codes:
  * ``0`` — gate passes (or escape hatch).
  * ``1`` — gate fails.

This script is intentionally stdlib-only so it runs without an
activated venv when pre-commit invokes it.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path classification
# ---------------------------------------------------------------------------

# Paths whose modification triggers the gate. POSIX prefixes; matched
# via str.startswith against the path-as-given-by-pre-commit.
_CODE_PREFIXES: tuple[str, ...] = (
    "src/specify_cli/",
    "extensions/linear/",
    "presets/linear/",
    "templates/commands/",
    "scripts/",
    "install-global/",
)

# Files in this set count as code-affecting on their own.
_CODE_FILES: frozenset[str] = frozenset(
    {
        "pyproject.toml",
    }
)

# Allowed docs — touching any one of these in the same commit satisfies
# the gate (per spec FR-024..FR-028).
_DOC_FILES: frozenset[str] = frozenset(
    {
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "VERSION.md",
    }
)

# Vendored upstream paths the gate ignores — they're owned by upstream
# and policed by the upstream-sync gate (T055). Keep in sync with
# ``tests/upstream-sync/test_src_specify_cli_unmodified.py::VENDORED_DIRS``.
_VENDORED_PREFIXES: tuple[str, ...] = (
    "src/specify_cli/",
    "templates/commands/",
    "integrations/",
    "extensions/git/",
    "extensions/selftest/",
    "extensions/template/",
    "presets/lean/",
    "presets/scaffold/",
    "presets/self-test/",
    "scripts/bash/",
    "scripts/powershell/",
)

# Paths the gate exempts even though they sit under a code prefix:
# tests, fixtures, governance harnesses — none ship as user-facing
# surface, so a test-only commit does not require a doc update.
_TEST_PREFIXES: tuple[str, ...] = (
    "tests/",
    "extensions/linear/tests/",
    "presets/linear/tests/",
)


_SKIP_DOCS_RE = re.compile(r"\[skip-docs\]", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _is_test_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _TEST_PREFIXES)


def _is_vendored(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _VENDORED_PREFIXES)


def _is_doc(path: str) -> bool:
    return path in _DOC_FILES


def _is_code_path(path: str) -> bool:
    if _is_test_path(path) or _is_vendored(path):
        return False
    if path in _CODE_FILES:
        return True
    return any(path.startswith(prefix) for prefix in _CODE_PREFIXES)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Constitution P9 gate: code changes need a doc update."
    )
    parser.add_argument(
        "--commit-msg",
        default="",
        help="Current commit message (for the [skip-docs] escape hatch). "
        "Used by the test suite; pre-commit uses --commit-msg-file.",
    )
    parser.add_argument(
        "--commit-msg-file",
        default=None,
        help="Path to a file containing the commit message (pre-commit "
        "passes .git/COMMIT_EDITMSG). Read at gate time; falls back to "
        "--commit-msg when the file is absent.",
    )
    parser.add_argument("paths", nargs="*", help="Staged file paths.")
    args = parser.parse_args(argv)

    commit_msg = args.commit_msg
    if args.commit_msg_file:
        msg_path = Path(args.commit_msg_file)
        if msg_path.exists():
            commit_msg = msg_path.read_text(encoding="utf-8", errors="replace")
    args.commit_msg = commit_msg

    # Normalize to POSIX-style strings (pre-commit emits them this way
    # on every supported platform, but be defensive).
    normalized = [str(Path(p).as_posix()) for p in args.paths]

    code_changes = [p for p in normalized if _is_code_path(p)]
    doc_changes = [p for p in normalized if _is_doc(p)]

    if not code_changes:
        return 0

    if doc_changes:
        return 0

    if _SKIP_DOCS_RE.search(args.commit_msg):
        # Audited escape hatch — emit a notice so it's visible in the
        # commit-time pre-commit output.
        print(
            "[docs-update] [skip-docs] marker present; bypassing P9 gate. "
            "Reviewer should confirm the intent.",
            file=sys.stderr,
        )
        return 0

    docs_list = ", ".join(sorted(_DOC_FILES))
    print(
        "[docs-update] Code-affecting paths changed without a user-facing doc update.\n"
        "[docs-update] Constitution P9 requires that code changes ship with at least\n"
        "[docs-update] one of: " + docs_list + ".\n"
        "[docs-update] Affected paths:\n"
        + "\n".join(f"[docs-update]   - {p}" for p in code_changes)
        + "\n[docs-update] Either update one of the listed docs in this same commit,\n"
        "[docs-update] or add `[skip-docs]` to the commit message (audited).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run(sys.argv[1:]))
