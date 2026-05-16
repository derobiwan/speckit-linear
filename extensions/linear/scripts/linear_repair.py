"""T060 — ``/speckit.linear.repair`` implementation.

Reconciles drift between the canonical Linear label set defined in
``linear-config.yml`` and the live label catalogue in the Linear
workspace. The scope is intentionally conservative:

  * Missing canonical ``speckit:<type>`` labels are created via
    ``create_issue_label`` with the canonical color from the config.
  * Existing canonical labels are left alone.
  * Feature labels that don't match the ``feature:NNN-<short-name>``
    regex are **reported** as drift; repair never silently rewrites
    them. The maintainer audits the surfaced list and decides whether
    to rename, archive, or delete.
  * The command is idempotent: a second run on a repaired workspace
    is a no-op (zero ``create_issue_label`` calls).

Constitution invariants:
  * P1 — no patches to ``src/specify_cli/``; this module lives behind
    the Linear extension.
  * P2 — Linear-first storage, no local fallback; if MCP fails, the
    caller's :class:`LinearMcpClientImpl` raises (we never write to
    disk on failure).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = ["RepairResult", "run"]


CANONICAL_SPECKIT_TYPES: tuple[str, ...] = (
    "spec",
    "plan",
    "research",
    "data-model",
    "contract",
    "quickstart",
    "checklist",
    "task",
    "constitution",
)

# Mirrors hook_helpers.FEATURE_LABEL_RE (kept local to avoid an import
# cycle and to keep this module standalone-testable).
_FEATURE_LABEL_RE = re.compile(r"^feature:(\d{3})-([a-z0-9-]+)$")


class _McpLike(Protocol):
    def call(self, tool: str, payload: dict) -> dict: ...


@dataclass(frozen=True)
class RepairResult:
    """Structured diff produced by :func:`run`.

    The command markdown reads these fields to render its output, so
    the schema is part of the public contract pinned by T059.
    """

    created_labels: list[str] = field(default_factory=list)
    existing_labels: list[str] = field(default_factory=list)
    feature_label_drift: list[dict[str, Any]] = field(default_factory=list)
    no_op: bool = False


def run(mcp: _McpLike, *, config: dict[str, Any]) -> RepairResult:
    """Execute the repair algorithm against ``mcp``.

    Args:
        mcp: A duck-typed Linear MCP client. The real
            :class:`LinearMcpClientImpl` satisfies the interface; tests
            pass an in-memory fake.
        config: Parsed ``linear-config.yml`` content. Required keys:
            ``labels.colors`` (mapping of canonical type → hex color).

    Returns:
        A :class:`RepairResult` describing every write performed and
        every drift entry discovered.
    """
    colors = (config.get("labels") or {}).get("colors") or {}

    response = mcp.call("list_issue_labels", {})
    existing = (response.get("data") or {}).get("labels") or []
    existing_by_name = {label.get("name"): label for label in existing}

    created: list[str] = []
    already_there: list[str] = []
    for speckit_type in CANONICAL_SPECKIT_TYPES:
        name = f"speckit:{speckit_type}"
        if name in existing_by_name:
            already_there.append(name)
            continue
        payload: dict[str, Any] = {"name": name}
        color = colors.get(speckit_type)
        if color:
            payload["color"] = color
        mcp.call("create_issue_label", payload)
        created.append(name)

    drift = _scan_feature_label_drift(existing)

    no_op = not created and not drift
    return RepairResult(
        created_labels=created,
        existing_labels=already_there,
        feature_label_drift=drift,
        no_op=no_op,
    )


def _scan_feature_label_drift(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return labels that *look* like feature labels but don't conform.

    Two heuristics flag drift:

      1. The name starts with ``feature:`` (lowercase) but does not
         match the canonical ``feature:NNN-<short-name>`` regex.
      2. The name starts with ``FEATURE:`` or ``Feature:`` (case
         drift) — almost certainly an authoring mistake; surfacing
         these lets the maintainer rename them.

    Returns:
        A list of dicts shaped ``{"id": ..., "name": ..., "reason": ...}``.
    """
    drift: list[dict[str, Any]] = []
    for label in labels:
        name = label.get("name") or ""
        if name.startswith("feature:"):
            if _FEATURE_LABEL_RE.match(name) is None:
                drift.append(
                    {
                        "id": label.get("id"),
                        "name": name,
                        "reason": "does not match feature:NNN-<short-name>",
                    }
                )
        elif name.lower().startswith("feature:"):
            # Case drift — the prefix isn't exactly "feature:".
            drift.append(
                {
                    "id": label.get("id"),
                    "name": name,
                    "reason": "prefix must be lowercase 'feature:'",
                }
            )
    return drift
