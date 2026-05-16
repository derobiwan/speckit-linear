#!/usr/bin/env bash
# T052: one-line installer for speckit-linear-skills (FR-003).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/derobiwan/speckit-linear-skills/main/install-global/install.sh | bash
#   # or with options:
#   curl -fsSL https://.../install.sh | bash -s -- --ai claude --here
#
# The script:
#   1. Ensures `uv` is on PATH (installs it from astral.sh if missing).
#   2. Installs/upgrades the `specify` CLI via `uv tool install`.
#   3. Auto-detects an available AI agent CLI using the precedence
#      claude > codex > gemini > copilot > opencode (or prompts on a
#      TTY when none is found / when AI is passed in).
#   4. Runs `specify init` with the chosen agent, applying `--preset
#      linear` (and `--extension linear` once that flag lands upstream;
#      until then the user can install the extension separately).
#
# Set INSTALL_DRY_RUN=1 to print the actions without executing.

set -Eeuo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
AI_AGENT=""
HERE=0
TARGET=""
NO_GIT=0
NO_PROMPT=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ai)        AI_AGENT="${2:-}"; shift 2 ;;
        --ai=*)      AI_AGENT="${1#*=}"; shift ;;
        --here)      HERE=1; shift ;;
        --target)    TARGET="${2:-}"; shift 2 ;;
        --target=*)  TARGET="${1#*=}"; shift ;;
        --no-git)    NO_GIT=1; shift ;;
        --no-prompt) NO_PROMPT=1; shift ;;
        -h|--help)
            sed -n '2,20p' "$0"
            exit 0
            ;;
        *)
            echo "install.sh: unknown argument: $1" >&2
            echo "Run with --help for usage." >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
say() { printf '[install.sh] %s\n' "$*"; }
warn() { printf '[install.sh] WARN: %s\n' "$*" >&2; }
fatal() { printf '[install.sh] ERROR: %s\n' "$*" >&2; exit 1; }

run() {
    if [[ "${INSTALL_DRY_RUN:-0}" == "1" ]]; then
        printf '[dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

# ---------------------------------------------------------------------------
# Step 1: ensure uv is installed
# ---------------------------------------------------------------------------
ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        say "uv detected ($(uv --version))"
        return 0
    fi
    say "Installing uv from astral.sh ..."
    # Official installer; pinned to https for transit integrity.
    run curl -fsSL https://astral.sh/uv/install.sh | run sh
    # The installer drops uv into ~/.local/bin by default; ensure PATH.
    export PATH="${HOME}/.local/bin:${PATH}"
    if ! command -v uv >/dev/null 2>&1; then
        fatal "uv install completed but 'uv' is still not on PATH. Add ~/.local/bin to PATH and re-run."
    fi
    say "uv installed: $(uv --version)"
}

# ---------------------------------------------------------------------------
# Step 2: install specify
# ---------------------------------------------------------------------------
install_specify() {
    say "Installing specify-cli via uv tool ..."
    # We install from PyPI by default; the .git URL form is the fallback
    # for users who want the bleeding edge of this fork.
    if [[ -n "${SPECIFY_SOURCE:-}" ]]; then
        run uv tool install --force "$SPECIFY_SOURCE"
    else
        run uv tool install --force speckit-linear-skills || \
            run uv tool install --force \
                'speckit-linear-skills @ git+https://github.com/derobiwan/speckit-linear-skills'
    fi
    if ! command -v specify >/dev/null 2>&1; then
        # uv tool installs land in ~/.local/bin (Linux/macOS); add to PATH.
        export PATH="${HOME}/.local/bin:${PATH}"
    fi
    command -v specify >/dev/null 2>&1 || fatal "specify not on PATH after install."
    say "specify installed: $(specify --version 2>&1 | head -n1)"
}

# ---------------------------------------------------------------------------
# Step 3: pick an AI agent
# ---------------------------------------------------------------------------
detect_agent() {
    if [[ -n "$AI_AGENT" ]]; then
        say "Using --ai $AI_AGENT (override)"
        return 0
    fi
    # Precedence per spec/task: claude > codex > gemini > copilot > opencode.
    for candidate in claude codex gemini copilot opencode; do
        if command -v "$candidate" >/dev/null 2>&1; then
            AI_AGENT="$candidate"
            say "Detected agent CLI: $candidate"
            return 0
        fi
    done
    # No agent detected — prompt only when STDIN is a TTY and --no-prompt
    # wasn't passed; otherwise default to copilot (no external CLI).
    if [[ "$NO_PROMPT" -eq 1 ]] || [[ ! -t 0 ]]; then
        AI_AGENT="copilot"
        warn "No agent CLI detected; defaulting to '$AI_AGENT' (no CLI required)."
        return 0
    fi
    printf 'No agent CLI detected. Enter an agent to use [copilot]: '
    read -r picked </dev/tty || picked=""
    AI_AGENT="${picked:-copilot}"
    say "Using agent: $AI_AGENT"
}

# ---------------------------------------------------------------------------
# Step 4: run specify init
# ---------------------------------------------------------------------------
run_specify_init() {
    local args=(init --integration "$AI_AGENT" --preset linear)
    [[ "$NO_GIT" -eq 1 ]] && args+=(--no-git)
    if [[ "$HERE" -eq 1 ]]; then
        args+=(--here)
    elif [[ -n "$TARGET" ]]; then
        args+=("$TARGET")
    fi
    say "Running: specify ${args[*]}"
    run specify "${args[@]}"
}

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
main() {
    say "speckit-linear-skills installer (FR-003)"
    ensure_uv
    install_specify
    detect_agent
    run_specify_init
    say "Done. Next: open the project, configure the Linear MCP server with"
    say "  claude mcp add --transport http linear https://mcp.linear.app/mcp"
    say "then use /speckit.specify in your agent."
}

main "$@"
