"""T062 — ``/speckit.linear.migrate`` implementation.

Ports v0.5.1 backlog-migration behaviour into the namespaced extension
layout. Given a list of legacy Linear issue ids and a feature short
name, the command:

  1. Resolves (or creates) the ``feature:NNN-<short>`` label using the
     same numbering algorithm as :func:`hook_helpers.ensure_feature_label`.
  2. Adds the dual labels ``speckit:task`` + ``feature:NNN-<short>``
     to each legacy issue via ``save_issue``, preserving any
     pre-existing labels (migrate adds, it never replaces).
  3. Skips issues that already wear both labels — making the operation
     idempotent on re-run.

Constitution invariants:
  * P1 — no patches to ``src/specify_cli/``.
  * P2 — Linear-first storage, no local fallback.
  * FR-010 — backward compatibility: this script powers both
    ``/speckit.linear.migrate`` and the plain ``/speckit.migrate``
    alias routed through the Linear preset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from extensions.linear.scripts.hook_helpers import ensure_feature_label

__all__ = ["MigrateResult", "run"]


_DEFAULT_SPECKIT_TYPE = "task"


class _McpLike(Protocol):
    def call(self, tool: str, payload: dict) -> dict: ...


@dataclass(frozen=True)
class MigrateResult:
    """Structured outcome of :func:`run`.

    Attributes:
        relabeled_issues: Issue ids whose labels were updated by this run.
        skipped_issues: Issue ids that already carried both labels.
        feature_label: The canonical ``feature:NNN-<short>`` label
            applied (or reused) for this migration.
        no_op: True when no ``save_issue`` writes were performed.
    """

    relabeled_issues: list[str] = field(default_factory=list)
    skipped_issues: list[str] = field(default_factory=list)
    feature_label: str = ""
    no_op: bool = False


def run(
    mcp: _McpLike,
    *,
    config: dict[str, Any],  # noqa: ARG001 — reserved for symmetry; FR-010 / future use
    feature_short_name: str,
    issue_ids: list[str],
) -> MigrateResult:
    """Relabel ``issue_ids`` with the dual ``speckit:<type>`` + ``feature:*`` set.

    Args:
        mcp: A duck-typed Linear MCP client.
        config: Parsed ``linear-config.yml`` (unused today; retained
            for parity with sibling commands and to keep FR-010 hook
            wiring stable when the spec evolves).
        feature_short_name: Kebab-case feature name without the NNN
            prefix; the numbering is assigned (or reused) automatically.
        issue_ids: Linear issue ids to migrate. Empty list → no-op.

    Returns:
        A :class:`MigrateResult` summary.
    """
    if not issue_ids:
        return MigrateResult(no_op=True)

    feature_label = ensure_feature_label(mcp, short_name=feature_short_name)
    feature_label_name = feature_label.get("name", "")
    speckit_label = f"speckit:{_DEFAULT_SPECKIT_TYPE}"

    relabeled: list[str] = []
    skipped: list[str] = []

    for issue_id in issue_ids:
        issue = _fetch_issue(mcp, issue_id)
        if issue is None:
            # Linear didn't return the issue — surface as skipped so the
            # caller's diff is complete, but don't raise (the wrapper
            # already retried per FR-032).
            skipped.append(issue_id)
            continue

        current_labels = list(issue.get("labels") or [])
        needs_update = (
            speckit_label not in current_labels
            or feature_label_name not in current_labels
        )
        if not needs_update:
            skipped.append(issue_id)
            continue

        new_labels = list(current_labels)
        if speckit_label not in new_labels:
            new_labels.append(speckit_label)
        if feature_label_name not in new_labels:
            new_labels.append(feature_label_name)

        mcp.call(
            "save_issue",
            {"id": issue_id, "labels": new_labels},
        )
        relabeled.append(issue_id)

    return MigrateResult(
        relabeled_issues=relabeled,
        skipped_issues=skipped,
        feature_label=feature_label_name,
        no_op=not relabeled,
    )


def _fetch_issue(mcp: _McpLike, issue_id: str) -> dict[str, Any] | None:
    """Return the Linear issue dict for ``issue_id``, or None if missing.

    Uses ``list_issues`` because that's the lowest-common-denominator
    read tool exposed by the fake MCP used in tests; in production the
    same call routes through the MCP client wrapper.
    """
    response = mcp.call("list_issues", {})
    for issue in (response.get("data") or {}).get("issues") or []:
        if issue.get("id") == issue_id:
            return issue
    return None
