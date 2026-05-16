# T052: one-line installer for speckit-linear-skills (FR-003) — PowerShell mirror of install.sh.
#
# Usage:
#   irm https://raw.githubusercontent.com/derobiwan/speckit-linear-skills/main/install-global/install.ps1 | iex
#   # or:
#   .\install.ps1 -Ai claude -Here
#
# Behaviour matches install.sh: install uv, install specify, auto-detect
# AI agent (precedence claude > codex > gemini > copilot > opencode), run
# `specify init --integration <agent> --preset linear`.

[CmdletBinding()]
param(
    [string]$Ai = "",
    [switch]$Here,
    [string]$Target = "",
    [switch]$NoGit,
    [switch]$NoPrompt
)

$ErrorActionPreference = "Stop"

function Write-Info($msg)  { Write-Host "[install.ps1] $msg" }
function Write-WarnLog($msg) { Write-Warning "[install.ps1] $msg" }
function Write-Fatal($msg) { Write-Error "[install.ps1] $msg"; exit 1 }

function Test-Command($name) {
    return [bool] (Get-Command $name -ErrorAction SilentlyContinue)
}

function Invoke-Step {
    param([scriptblock]$Block, [string]$Description)
    if ($env:INSTALL_DRY_RUN -eq "1") {
        Write-Info "[dry-run] $Description"
    } else {
        & $Block
    }
}

# ---------------------------------------------------------------------------
# Step 1: ensure uv is installed
# ---------------------------------------------------------------------------
function Ensure-Uv {
    if (Test-Command "uv") {
        Write-Info "uv detected ($(uv --version))"
        return
    }
    Write-Info "Installing uv from astral.sh ..."
    Invoke-Step {
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    } "Run astral.sh uv installer"

    # uv lands in $env:USERPROFILE\.local\bin; add to PATH for this session.
    $localBin = Join-Path $env:USERPROFILE ".local\bin"
    if (-not ($env:PATH -split ';' | Where-Object { $_ -eq $localBin })) {
        $env:PATH = "$localBin;$env:PATH"
    }
    if (-not (Test-Command "uv")) {
        Write-Fatal "uv install completed but uv is still not on PATH."
    }
    Write-Info "uv installed: $(uv --version)"
}

# ---------------------------------------------------------------------------
# Step 2: install specify
# ---------------------------------------------------------------------------
function Install-Specify {
    Write-Info "Installing specify-cli via uv tool ..."
    $source = $env:SPECIFY_SOURCE
    if (-not $source) {
        $source = "speckit-linear-skills"
    }
    Invoke-Step {
        try {
            uv tool install --force $source
        } catch {
            # Fallback to the git source for the bleeding edge.
            uv tool install --force "speckit-linear-skills @ git+https://github.com/derobiwan/speckit-linear-skills"
        }
    } "uv tool install $source"

    # Ensure uv's bin dir is on PATH for this session.
    $uvBin = Join-Path $env:USERPROFILE ".local\bin"
    if (-not ($env:PATH -split ';' | Where-Object { $_ -eq $uvBin })) {
        $env:PATH = "$uvBin;$env:PATH"
    }
    if (-not (Test-Command "specify")) {
        Write-Fatal "specify not on PATH after install."
    }
    Write-Info "specify installed."
}

# ---------------------------------------------------------------------------
# Step 3: pick an AI agent
# ---------------------------------------------------------------------------
function Detect-Agent {
    if ($Ai) {
        Write-Info "Using --ai $Ai (override)"
        return $Ai
    }
    foreach ($candidate in @("claude", "codex", "gemini", "copilot", "opencode")) {
        if (Test-Command $candidate) {
            Write-Info "Detected agent CLI: $candidate"
            return $candidate
        }
    }
    if ($NoPrompt -or -not ([Environment]::UserInteractive)) {
        Write-WarnLog "No agent CLI detected; defaulting to 'copilot'."
        return "copilot"
    }
    $picked = Read-Host "No agent CLI detected. Enter agent to use [copilot]"
    if (-not $picked) { $picked = "copilot" }
    Write-Info "Using agent: $picked"
    return $picked
}

# ---------------------------------------------------------------------------
# Step 4: run specify init
# ---------------------------------------------------------------------------
function Run-SpecifyInit($agent) {
    $args = @("init", "--integration", $agent, "--preset", "linear")
    if ($NoGit) { $args += "--no-git" }
    if ($Here) {
        $args += "--here"
    } elseif ($Target) {
        $args += $Target
    }
    Write-Info "Running: specify $($args -join ' ')"
    Invoke-Step { specify @args } "specify init"
}

# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
function Main {
    Write-Info "speckit-linear-skills installer (FR-003)"
    Ensure-Uv
    Install-Specify
    $agent = Detect-Agent
    Run-SpecifyInit $agent
    Write-Info "Done. Next: open the project, configure the Linear MCP server with"
    Write-Info "  claude mcp add --transport http linear https://mcp.linear.app/mcp"
    Write-Info "then use /speckit.specify in your agent."
}

Main
