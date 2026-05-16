"""Integration tests for ``/speckit.linear.migrate`` (T061, e2e).

End-to-end migration scenarios that exercise the script via an
in-memory MCP fake mirroring the wire-shape of the Linear MCP server.

Acceptance criterion from PMO-138 (T061): a legacy backlog is relabeled
with the dual ``speckit:*`` + ``feature:NNN-name`` convention and the
operation is idempotent on re-run.
"""

from __future__ import annotations

import pytest

linear_migrate_module = pytest.importorskip(
    "extensions.linear.scripts.linear_migrate",
    reason="T062 implementation not yet present — expected during RED phase.",
)
run_migrate = linear_migrate_module.run


class FakeLinearMcp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.labels: list[dict] = []
        self.issues: list[dict] = []
        self._next_id = 0

    def call(self, tool: str, payload: dict) -> dict:
        self.calls.append((tool, payload))
        if tool == "list_issue_labels":
            return {"data": {"labels": list(self.labels)}}
        if tool == "create_issue_label":
            label = {"id": self._mint_id("lbl"), **payload}
            self.labels.append(label)
            return {"data": {"label": label}}
        if tool == "list_issues":
            return {"data": {"issues": list(self.issues)}}
        if tool == "save_issue":
            issue_id = payload.get("id") or self._mint_id("iss")
            for existing in self.issues:
                if existing["id"] == issue_id:
                    existing.update(payload)
                    return {"data": {"issue": existing}}
            issue = {"id": issue_id, **payload}
            self.issues.append(issue)
            return {"data": {"issue": issue}}
        raise NotImplementedError(f"FakeLinearMcp does not support {tool!r}")

    def _mint_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"


# ---------------------------------------------------------------------------
# Scenario: legacy backlog (no speckit:* labels) gets relabeled
# ---------------------------------------------------------------------------


def test_legacy_backlog_gets_relabeled_in_place(linear_config):
    mcp = FakeLinearMcp()
    mcp.issues.extend(
        [
            {
                "id": "PMO-100",
                "title": "Old work item 1",
                "labels": [],
                "project": "speckit-linear-skills",
            },
            {
                "id": "PMO-101",
                "title": "Old work item 2",
                "labels": ["legacy"],
                "project": "speckit-linear-skills",
            },
        ]
    )

    result = run_migrate(
        mcp,
        config=linear_config,
        feature_short_name="payment-flow",
        issue_ids=["PMO-100", "PMO-101"],
    )

    assert sorted(result.relabeled_issues) == ["PMO-100", "PMO-101"]
    assert result.feature_label.startswith("feature:")
    assert result.feature_label.endswith("-payment-flow")

    for issue_id in ("PMO-100", "PMO-101"):
        issue = next(i for i in mcp.issues if i["id"] == issue_id)
        assert "speckit:task" in issue["labels"]
        assert result.feature_label in issue["labels"]


# ---------------------------------------------------------------------------
# Scenario: idempotency on re-run
# ---------------------------------------------------------------------------


def test_rerun_is_no_op_after_initial_migration(linear_config):
    mcp = FakeLinearMcp()
    mcp.issues.append(
        {
            "id": "PMO-100",
            "title": "Item",
            "labels": [],
            "project": "speckit-linear-skills",
        }
    )

    run_migrate(
        mcp,
        config=linear_config,
        feature_short_name="payment-flow",
        issue_ids=["PMO-100"],
    )
    mcp.calls.clear()

    second = run_migrate(
        mcp,
        config=linear_config,
        feature_short_name="payment-flow",
        issue_ids=["PMO-100"],
    )

    saves = [c for c in mcp.calls if c[0] == "save_issue"]
    assert saves == []
    assert second.no_op is True
    assert second.relabeled_issues == []
    assert second.skipped_issues == ["PMO-100"]
