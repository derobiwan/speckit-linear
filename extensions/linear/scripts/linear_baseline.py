"""T064 — ``/speckit.linear.baseline`` implementation.

Analyzes an existing source code directory and produces a ``[SPEC]``
issue describing the discovered features. Ports v0.5.1 baseline
behaviour into the namespaced extension layout.

Algorithm:

  1. Walk ``source_dir/src/*`` (the common Python project root). Each
     immediate subdirectory containing source files is treated as a
     discovered feature. README/Markdown/dotfiles are ignored.
  2. Resolve (or create) the canonical ``feature:NNN-<short>`` label
     via :func:`hook_helpers.ensure_feature_label`.
  3. Persist a single ``[SPEC]`` issue with dual labels
     (``speckit:spec`` + the feature label). Re-running on the same
     source updates the issue in place (same id), making the
     operation idempotent.

Constitution invariants:
  * P1 — no patches to ``src/specify_cli/``.
  * P2 — Linear-first storage, no local fallback.
  * FR-010 — this script powers both ``/speckit.linear.baseline``
    and the plain ``/speckit.baseline`` alias routed through the
    Linear preset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from extensions.linear.scripts.hook_helpers import (
    dual_labels,
    ensure_feature_label,
)

__all__ = ["BaselineResult", "run"]


# Filename suffixes we consider "source" for feature discovery.
_SOURCE_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rs"}
)


class _McpLike(Protocol):
    def call(self, tool: str, payload: dict) -> dict: ...


@dataclass(frozen=True)
class BaselineResult:
    """Structured outcome of :func:`run`.

    Attributes:
        discovered_features: List of ``{"name": str, "path": str}`` entries
            describing each feature found under ``source_dir``.
        spec_issue_id: Linear id of the persisted ``[SPEC]`` issue,
            or ``None`` when ``discovered_features`` is empty.
        feature_label: Canonical ``feature:NNN-<short>`` label applied.
        no_op: True when no features were discovered (nothing persisted).
    """

    discovered_features: list[dict[str, str]] = field(default_factory=list)
    spec_issue_id: str | None = None
    feature_label: str = ""
    no_op: bool = False


def run(
    mcp: _McpLike,
    *,
    config: dict[str, Any],  # noqa: ARG001 — reserved for symmetry / FR-010
    source_dir: Path,
    feature_short_name: str,
) -> BaselineResult:
    """Scan ``source_dir`` and persist a baseline ``[SPEC]`` issue.

    Args:
        mcp: Linear MCP client.
        config: Parsed ``linear-config.yml`` (unused today; retained
            for parity with sibling commands).
        source_dir: Project root to analyze. ``source_dir/src/*`` is
            walked; absence of ``src/`` produces an empty result.
        feature_short_name: Kebab-case feature name without the NNN
            prefix; baseline assigns the numbering automatically.

    Returns:
        A :class:`BaselineResult` summary.
    """
    source_dir = Path(source_dir)
    discovered = _discover_features(source_dir)

    if not discovered:
        return BaselineResult(no_op=True)

    feature_label = ensure_feature_label(mcp, short_name=feature_short_name)
    feature_label_name = feature_label.get("name", "")
    # Derive the NNN-name segment from the label so the dual-labels
    # helper accepts it.
    feature_segment = feature_label_name.removeprefix("feature:")
    labels = dual_labels(speckit_type="spec", feature=feature_segment)

    existing_id = _existing_spec_id(mcp, feature_label_name)

    title = _format_title(feature_segment, feature_short_name)
    description = _format_body(discovered, feature_short_name)
    payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "labels": labels,
    }
    if existing_id is not None:
        payload["id"] = existing_id

    response = mcp.call("save_issue", payload)
    issue = (response.get("data") or {}).get("issue") or {}
    spec_id = issue.get("id") or existing_id

    return BaselineResult(
        discovered_features=discovered,
        spec_issue_id=spec_id,
        feature_label=feature_label_name,
        no_op=False,
    )


# ---------------------------------------------------------------------------
# Feature discovery
# ---------------------------------------------------------------------------


def _discover_features(source_dir: Path) -> list[dict[str, str]]:
    """Return one entry per immediate subdirectory of ``source_dir/src``
    that contains at least one recognized source file.
    """
    src_root = source_dir / "src"
    if not src_root.is_dir():
        return []
    features: list[dict[str, str]] = []
    for child in sorted(src_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name.startswith("_"):
            continue
        if not _contains_source(child):
            continue
        features.append(
            {"name": child.name, "path": str(child.relative_to(source_dir))}
        )
    return features


def _contains_source(directory: Path) -> bool:
    for entry in directory.rglob("*"):
        if entry.is_file() and entry.suffix in _SOURCE_SUFFIXES:
            return True
    return False


# ---------------------------------------------------------------------------
# Existing spec lookup (for idempotent re-runs)
# ---------------------------------------------------------------------------


def _existing_spec_id(mcp: _McpLike, feature_label_name: str) -> str | None:
    """Return the id of the existing ``[SPEC]`` issue for ``feature_label_name``,
    or ``None`` when no such issue exists yet.
    """
    response = mcp.call("list_issues", {"label": feature_label_name})
    for issue in (response.get("data") or {}).get("issues") or []:
        labels = issue.get("labels") or []
        if "speckit:spec" in labels:
            return issue.get("id")
    return None


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _format_title(feature_segment: str, short_name: str) -> str:
    number = feature_segment.split("-", 1)[0]
    return f"[SPEC] {number}: {short_name}"


def _format_body(features: list[dict[str, str]], short_name: str) -> str:
    lines = [
        f"# Baseline Specification: {short_name}",
        "",
        "Generated by `/speckit.linear.baseline` from the existing source tree.",
        "",
        "## Discovered Features",
        "",
    ]
    for feature in features:
        lines.append(f"- **{feature['name']}** — `{feature['path']}`")
    lines.append("")
    return "\n".join(lines)
