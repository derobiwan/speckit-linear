#!/usr/bin/env bash
# T058 — Maintainer helper: refresh the vendored upstream tree.
#
# Usage:
#   scripts/maintainer/sync-upstream.sh <upstream-tag>           # e.g. v0.9.0
#   scripts/maintainer/sync-upstream.sh v0.9.0 --dry-run
#   scripts/maintainer/sync-upstream.sh v0.9.0 --upstream-url <git-url>
#
# What it does (in order):
#
#   1. Clones the upstream tag into a tmp dir.
#   2. Rsyncs the vendored top-level paths into this repo with
#      `--delete` so files removed upstream are removed locally.
#   3. Writes the new tag + resolved commit SHA to .specify/upstream.pin.
#   4. Prints a summary so the maintainer can immediately run `pytest`.
#
# What it does NOT do (Constitution P1 / FR-013):
#
#   * Touch extensions/linear/ or presets/linear/ — the fork's
#     contribution.
#   * Touch tests/, install-global/, scripts/maintainer/.
#   * Commit anything — the maintainer reviews the diff before
#     committing.
#
# The list of vendored paths is intentionally duplicated here and in
# tests/upstream-sync/test_src_specify_cli_unmodified.py::VENDORED_DIRS.
# When upstream adds a vendored path, update BOTH places (and the
# pre-commit exclude regex, see CONTRIBUTING.md "Syncing with upstream").

set -Eeuo pipefail

DEFAULT_UPSTREAM_URL="https://github.com/github/spec-kit.git"

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
UPSTREAM_TAG=""
UPSTREAM_URL="$DEFAULT_UPSTREAM_URL"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --upstream-url) UPSTREAM_URL="${2:-}"; shift 2 ;;
        --upstream-url=*) UPSTREAM_URL="${1#*=}"; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help)
            sed -n '2,28p' "$0"
            exit 0
            ;;
        -*)
            echo "sync-upstream.sh: unknown flag: $1" >&2
            exit 2
            ;;
        *)
            if [[ -n "$UPSTREAM_TAG" ]]; then
                echo "sync-upstream.sh: extra positional arg: $1" >&2
                exit 2
            fi
            UPSTREAM_TAG="$1"
            shift
            ;;
    esac
done

if [[ -z "$UPSTREAM_TAG" ]]; then
    echo "sync-upstream.sh: missing required <upstream-tag>" >&2
    echo "Usage: $0 <tag> [--dry-run] [--upstream-url <url>]" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
say()  { printf '[sync-upstream] %s\n' "$*"; }
warn() { printf '[sync-upstream] WARN: %s\n' "$*" >&2; }
fatal() { printf '[sync-upstream] ERROR: %s\n' "$*" >&2; exit 1; }

run() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf '[dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || fatal "$1 not on PATH"
}

# ---------------------------------------------------------------------------
# Prereqs
# ---------------------------------------------------------------------------
require_cmd git
require_cmd rsync

REPO_ROOT="$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Vendored paths (mirror VENDORED_DIRS in the test)
# ---------------------------------------------------------------------------
VENDORED_DIRS=(
    "src/specify_cli"
    "templates/commands"
    "integrations"
    "extensions/git"
    "extensions/selftest"
    "extensions/template"
    "presets/lean"
    "presets/scaffold"
    "presets/self-test"
    "scripts/bash"
    "scripts/powershell"
)

# ---------------------------------------------------------------------------
# 1) Clone upstream at the tag into a tmp dir
# ---------------------------------------------------------------------------
TMP_DIR="$(mktemp -d -t speckit-sync-upstream.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

say "Cloning $UPSTREAM_URL @ $UPSTREAM_TAG ..."
run git clone --quiet --depth=1 --branch "$UPSTREAM_TAG" "$UPSTREAM_URL" "$TMP_DIR/spec-kit"

UPSTREAM_CHECKOUT="$TMP_DIR/spec-kit"

# Resolve the tag → SHA so we can pin both. Dry-run mode never cloned,
# so substitute a placeholder for the summary print.
if [[ "$DRY_RUN" -eq 1 ]]; then
    UPSTREAM_SHA="<dry-run-no-clone>"
else
    UPSTREAM_SHA="$(git -C "$UPSTREAM_CHECKOUT" rev-parse HEAD)"
fi
say "Resolved $UPSTREAM_TAG → $UPSTREAM_SHA"

# ---------------------------------------------------------------------------
# 2) Rsync vendored dirs
# ---------------------------------------------------------------------------
for dir in "${VENDORED_DIRS[@]}"; do
    src="$UPSTREAM_CHECKOUT/$dir/"
    dest="$REPO_ROOT/$dir/"
    if [[ ! -d "$UPSTREAM_CHECKOUT/$dir" ]]; then
        warn "upstream is missing vendored path: $dir (skipping)"
        continue
    fi
    say "Refreshing $dir ..."
    # --delete: remove local files that no longer exist upstream.
    # --exclude __pycache__: never copy cached bytecode.
    run rsync -a --delete \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='*.pyo' \
        "$src" "$dest"
done

# ---------------------------------------------------------------------------
# 3) Pin the new tag + SHA
# ---------------------------------------------------------------------------
PIN_FILE="$REPO_ROOT/.specify/upstream.pin"
if [[ "$DRY_RUN" -eq 0 ]]; then
    printf '%s\n%s\n' "$UPSTREAM_TAG" "$UPSTREAM_SHA" > "$PIN_FILE"
    say "Updated $PIN_FILE"
else
    say "[dry-run] would write to $PIN_FILE:"
    printf '  %s\n  %s\n' "$UPSTREAM_TAG" "$UPSTREAM_SHA"
fi

# ---------------------------------------------------------------------------
# 4) Summary
# ---------------------------------------------------------------------------
say "Done. Next steps:"
say "  1. Review the diff: git status && git diff --stat"
say "  2. Run the test suite: pytest"
say "  3. Ensure tests/upstream-sync passes (Constitution P1 gate)."
say "  4. Bump VERSION.md / pyproject.toml if needed, then commit."
