"""Integration tests for ``/speckit.linear.repair`` (T059, e2e).

These tests exercise the full repair flow through an in-memory MCP fake
that mimics the wire-level shape of the Linear MCP server. We do not use
a VCR cassette here because the repair logic is itself the unit-under-test
at the boundary — VCR is reserved for callers that go through the real
:class:`LinearMcpClientImpl` HTTP layer (see ``test_mcp_client.py``).

The e2e scenarios assert:

  * A workspace with no canonical labels is fully repaired in one pass.
  * A workspace with a mix of canonical labels and drifted feature labels
    yields a structured diff that the agent can print verbatim.
  * Running repair twice in a row is a no-op on the second invocation
    (idempotency — see acceptance criterion in PMO-136).
"""

from __future__ import annotations

import pytest

linear_repair_module = pytest.importorskip(
    "extensions.linear.scripts.linear_repair",
    reason="T060 implementation not yet present — expected during RED phase.",
)
run_repair = linear_repair_module.run


CANONICAL_SPECKIT_TYPES = (
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


class FakeLinearMcp:
    """Wire-shape fake used by the integration suite.

    Mirrors the response envelopes returned by the real MCP server for
    the small subset of tools repair touches.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.labels: list[dict] = []
        self._next_id = 0

    def call(self, tool: str, payload: dict) -> dict:
        self.calls.append((tool, payload))
        if tool == "list_issue_labels":
            return {"data": {"labels": list(self.labels)}}
        if tool == "create_issue_label":
            label = {"id": self._mint_id("lbl"), **payload}
            self.labels.append(label)
            return {"data": {"label": label}}
        raise NotImplementedError(f"FakeLinearMcp does not support {tool!r}")

    def _mint_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"


# ---------------------------------------------------------------------------
# Scenario: virgin workspace
# ---------------------------------------------------------------------------


def test_virgin_workspace_creates_full_canonical_set(linear_config):
    mcp = FakeLinearMcp()
    result = run_repair(mcp, config=linear_config)

    assert len(result.created_labels) == len(CANONICAL_SPECKIT_TYPES)
    assert result.existing_labels == []
    assert result.feature_label_drift == []
    assert result.no_op is False


# ---------------------------------------------------------------------------
# Scenario: mixed state with drifted feature labels
# ---------------------------------------------------------------------------


def test_mixed_state_reports_drift_alongside_creations(linear_config):
    mcp = FakeLinearMcp()
    mcp.labels.extend(
        [
            # Partial canonical coverage.
            {"id": "lbl-1", "name": "speckit:spec", "color": "#10B981"},
            {"id": "lbl-2", "name": "speckit:plan", "color": "#3B82F6"},
            # One compliant, two drifted feature labels.
            {"id": "lbl-3", "name": "feature:001-user-auth"},
            {"id": "lbl-4", "name": "feature:bad-shape"},
            {"id": "lbl-5", "name": "FEATURE:002-uppercase-prefix"},
        ]
    )

    result = run_repair(mcp, config=linear_config)

    # Created the missing 7 canonical types.
    assert sorted(result.created_labels) == sorted(
        f"speckit:{t}" for t in CANONICAL_SPECKIT_TYPES if t not in ("spec", "plan")
    )

    drift_names = {d["name"] for d in result.feature_label_drift}
    assert "feature:001-user-auth" not in drift_names
    assert "feature:bad-shape" in drift_names
    # FEATURE:* with uppercase prefix is not a feature label at all,
    # but the drift detector must surface it because it likely indicates
    # an authoring error (R6 — surface drift, never silently rewrite).
    assert "FEATURE:002-uppercase-prefix" in drift_names


# ---------------------------------------------------------------------------
# Scenario: idempotency (T059 acceptance criterion)
# ---------------------------------------------------------------------------


def test_repair_is_idempotent_e2e(linear_config):
    mcp = FakeLinearMcp()

    run_repair(mcp, config=linear_config)
    mcp.calls.clear()
    second = run_repair(mcp, config=linear_config)

    creates = [c for c in mcp.calls if c[0] == "create_issue_label"]
    assert creates == []
    assert second.created_labels == []
    assert second.no_op is True
