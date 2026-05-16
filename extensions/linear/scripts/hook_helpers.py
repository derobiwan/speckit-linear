"""T027 — Shared helpers used by every Linear before_/after_ hook.

These are intentionally pure functions that take an MCP-client-like
object as their first parameter (duck-typed: any object exposing
``call(tool: str, payload: dict) -> dict``). The real
:class:`LinearMcpClientImpl` from
:mod:`extensions.linear.scripts.linear_mcp_client` satisfies this
interface; tests pass an in-memory fake.

Design notes:
  * No filesystem I/O except via the ``config_path`` argument to
    :func:`find_active_feature`. Hook scripts pass the resolved
    ``.specify/config/linear.md`` path explicitly so this module stays
    test-friendly.
  * No retry logic here — that lives in
    :class:`LinearMcpClientImpl`. The helpers issue exactly one call
    per logical operation and let the MCP client handle transient
    failures per Contract C4.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any, Protocol, TextIO

__all__ = [
    "FeatureLabelFormatError",
    "ProductProjectNotFoundError",
    "UnknownSpeckitTypeError",
    "dual_labels",
    "emit_backend_line",
    "ensure_feature_label",
    "find_active_feature",
    "idempotency_key",
    "resolve_product_project",
]


CANONICAL_SPECKIT_TYPES = frozenset(
    {
        "spec",
        "plan",
        "research",
        "data-model",
        "contract",
        "quickstart",
        "checklist",
        "task",
        "constitution",
    }
)

FEATURE_LABEL_RE = re.compile(r"^feature:(\d{3})-([a-z0-9-]+)$")
SHORT_NAME_WITH_NUMBER_RE = re.compile(r"^\d{3}-[a-z0-9-]+$")
BRANCH_FEATURE_RE = re.compile(r"^(\d{3}-[a-z0-9-]+)$")


class HookHelperError(Exception):
    """Base class for hook-helper exceptions."""


class FeatureLabelFormatError(HookHelperError):
    """Raised when a feature short-name doesn't match the NNN-name pattern."""


class UnknownSpeckitTypeError(HookHelperError):
    """Raised when a caller asks for an unrecognized speckit:* type label."""


class ProductProjectNotFoundError(HookHelperError):
    """Raised when resolve_product_project can't find a match and create_if_missing is False."""


class _McpLike(Protocol):
    def call(self, tool: str, payload: dict) -> dict: ...


# ---------------------------------------------------------------------------
# Feature labels
# ---------------------------------------------------------------------------


def ensure_feature_label(mcp: _McpLike, *, short_name: str) -> dict[str, Any]:
    """Return (creating if necessary) the feature label for ``short_name``.

    Algorithm:
      1. List existing labels via ``list_issue_labels``.
      2. If a label named ``feature:NNN-<short_name>`` exists, return it.
      3. Otherwise compute the next sequential number (max existing + 1,
         starting at 1), create ``feature:NNN-<short_name>``, and return it.

    Args:
        mcp: Linear MCP client.
        short_name: kebab-case feature short name without the NNN prefix.

    Returns:
        The label dict as returned by the MCP server.
    """
    if "/" in short_name or " " in short_name:
        raise FeatureLabelFormatError(
            f"Invalid feature short name {short_name!r}: kebab-case only"
        )

    existing_response = mcp.call("list_issue_labels", {})
    labels = existing_response.get("data", {}).get("labels", [])

    feature_numbers: list[int] = []
    for label in labels:
        match = FEATURE_LABEL_RE.match(label.get("name", ""))
        if not match:
            continue
        number = int(match.group(1))
        name_part = match.group(2)
        if name_part == short_name:
            return label
        feature_numbers.append(number)

    next_number = (max(feature_numbers) + 1) if feature_numbers else 1
    label_name = f"feature:{next_number:03d}-{short_name}"
    created = mcp.call("create_issue_label", {"name": label_name})
    return created.get("data", {}).get("label", created)


# ---------------------------------------------------------------------------
# Product project
# ---------------------------------------------------------------------------


def resolve_product_project(
    mcp: _McpLike, *, name: str, create_if_missing: bool = False
) -> dict[str, Any]:
    """Find a project by name (case-insensitive); optionally create it.

    Args:
        mcp: Linear MCP client.
        name: Project name to resolve.
        create_if_missing: When True, create the project if no match found.

    Raises:
        ProductProjectNotFoundError: When no match and ``create_if_missing``
            is False.
    """
    response = mcp.call("list_projects", {"name": name})
    projects = response.get("data", {}).get("projects", [])
    target_lower = name.lower()
    for project in projects:
        if project.get("name", "").lower() == target_lower:
            return project

    if not create_if_missing:
        raise ProductProjectNotFoundError(
            f"Linear project {name!r} not found and create_if_missing=False"
        )

    created = mcp.call("save_project", {"name": name})
    return created.get("data", {}).get("project", created)


# ---------------------------------------------------------------------------
# Dual labels
# ---------------------------------------------------------------------------


def dual_labels(*, speckit_type: str, feature: str) -> list[str]:
    """Return the two-label set that every speckit-managed issue must wear.

    Args:
        speckit_type: One of the canonical types
            (spec/plan/research/data-model/contract/quickstart/
            checklist/task/constitution).
        feature: Feature short name, including the ``NNN-`` prefix
            (e.g., ``001-user-auth``).

    Raises:
        UnknownSpeckitTypeError: When ``speckit_type`` is not in the
            canonical set.
        FeatureLabelFormatError: When ``feature`` is missing the NNN prefix.
    """
    if speckit_type not in CANONICAL_SPECKIT_TYPES:
        raise UnknownSpeckitTypeError(
            f"Unknown speckit type {speckit_type!r}; "
            f"expected one of {sorted(CANONICAL_SPECKIT_TYPES)}"
        )
    if not SHORT_NAME_WITH_NUMBER_RE.match(feature):
        raise FeatureLabelFormatError(
            f"Feature label segment {feature!r} must match NNN-shortname"
        )
    return [f"speckit:{speckit_type}", f"feature:{feature}"]


# ---------------------------------------------------------------------------
# Idempotency keys
# ---------------------------------------------------------------------------


def idempotency_key(operation: str, feature: str, artifact_id: str) -> str:
    """Build a deterministic idempotency key for retryable Linear writes.

    Format: ``speckit:<operation>:<sha256-12>``. The hash includes all
    three components so changing any one yields a distinct key while
    keeping the value small enough for Linear's ``idempotency_key``
    parameter (typically < 64 chars).
    """
    raw = f"{operation}|{feature}|{artifact_id}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:12]
    return f"speckit:{operation}:{digest}"


# ---------------------------------------------------------------------------
# Active feature discovery
# ---------------------------------------------------------------------------


def find_active_feature(
    *,
    mcp: _McpLike,
    config_path: Path | None,
    git_branch: str | None,
) -> str | None:
    """Locate the active feature short name (``NNN-name``).

    Resolution order (per .specify/config/linear.md "Find Active Feature"):
      1. Explicit ``feature:NNN-name`` line in ``config_path``.
      2. Git branch matching ``NNN-name``.
      3. Returns ``None`` — caller asks the user.

    ``mcp`` is accepted for symmetry with future label-scan fallback;
    not used in the current resolver. We keep the parameter to avoid
    a churn-y signature change later.
    """
    _ = mcp  # reserved for label-scan fallback
    if config_path is not None and config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            match = FEATURE_LABEL_RE.match(line)
            if match:
                return f"{match.group(1)}-{match.group(2)}"

    if git_branch:
        match = BRANCH_FEATURE_RE.match(git_branch.strip())
        if match:
            return match.group(1)

    return None


# ---------------------------------------------------------------------------
# Backend confirmation line (FR-022 / Contract C1) — T053
# ---------------------------------------------------------------------------

# Per-process sentinel of ``(workspace, project)`` pairs we've already
# emitted a confirmation line for. Switching to a different workspace or
# project within the same process re-emits; a duplicate call for the
# same target is a no-op. ``hook_helpers`` is the natural home because
# every before-hook imports it and emits before any MCP write.
_BACKEND_LINE_EMITTED: set[tuple[str, str]] = set()


def _quote_if_needed(value: str) -> str:
    """Wrap whitespace-bearing values in single quotes for readability."""
    return f"'{value}'" if any(ch.isspace() for ch in value) else value


def emit_backend_line(
    workspace: str,
    project: str,
    *,
    stream: TextIO | None = None,
) -> None:
    """Emit the FR-022 backend confirmation line exactly once per target.

    Format (Contract C1 §"Verbosity & logging contract"):

        [linear] backend=Linear workspace=<team-name> project=<project-name>

    The line lands on stderr (or ``stream`` when supplied — tests pass
    a buffer). A per-process sentinel ensures that re-calling with the
    same ``(workspace, project)`` is a silent no-op, while switching to
    a different target re-emits.

    Args:
        workspace: Linear team / workspace name.
        project: Linear project name.
        stream: Optional override of the output stream. Defaults to
            ``sys.stderr`` resolved at call time so test monkeypatching
            of ``sys.stderr`` is respected.
    """
    key = (workspace, project)
    if key in _BACKEND_LINE_EMITTED:
        return
    _BACKEND_LINE_EMITTED.add(key)
    ws = _quote_if_needed(workspace)
    pj = _quote_if_needed(project)
    out = stream if stream is not None else sys.stderr
    out.write(f"[linear] backend=Linear workspace={ws} project={pj}\n")
    # Best-effort flush so the line is visible before subsequent MCP
    # output. We swallow stream errors — many test buffers don't flush.
    try:
        out.flush()
    except Exception:
        pass
