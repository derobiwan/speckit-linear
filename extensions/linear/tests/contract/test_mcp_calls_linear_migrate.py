"""Contract tests for ``/speckit.linear.migrate`` (T061).

The migrate command ports v0.5.1 backlog migration behaviour into the
namespaced extension layout. Per the Phase 6 acceptance for T061:

  * A legacy backlog (issues without the dual ``speckit:*`` +
    ``feature:NNN-name`` labels) is relabeled in place.
  * The migration is idempotent — a second run on the just-migrated
    state produces zero writes.
  * The command preserves issue identity (uses ``save_issue`` with the
    existing id, never re-creates).

These tests pin the public surface of
``extensions.linear.scripts.linear_migrate`` BEFORE the implementation
lands (Constitution P4 — Test-First, NON-NEGOTIABLE).

The MCP boundary is exercised with the same in-memory ``FakeLinearMcp``
shape used by the other contract suites; VCR-backed wire tests live
under ``integration/test_linear_migrate_e2e.py``.
"""

from __future__ import annotations

import pytest

linear_migrate_module = pytest.importorskip(
    "extensions.linear.scripts.linear_migrate",
    reason="T062 implementation not yet present — expected during RED phase.",
)
run_migrate = linear_migrate_module.run
MigrateResult = linear_migrate_module.MigrateResult


# ---------------------------------------------------------------------------
# Fake MCP
# ---------------------------------------------------------------------------


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
            label_filter = payload.get("label")
            project_filter = payload.get("project")
            results = []
            for issue in self.issues:
                if label_filter and label_filter not in issue.get("labels", []):
                    continue
                if project_filter and issue.get("project") != project_filter:
                    continue
                results.append(issue)
            return {"data": {"issues": results}}
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
# Contract: feature label creation + reuse
# ---------------------------------------------------------------------------


class TestEnsuresFeatureLabel:
    def test_creates_feature_label_when_missing(self, linear_config):
        mcp = FakeLinearMcp()
        # A single legacy issue belonging to feature 001.
        mcp.issues.append(
            {
                "id": "PMO-100",
                "title": "Legacy ticket",
                "labels": [],
                "project": "speckit-linear-skills",
            }
        )

        run_migrate(
            mcp,
            config=linear_config,
            feature_short_name="user-auth",
            issue_ids=["PMO-100"],
        )

        created = [c for c in mcp.calls if c[0] == "create_issue_label"]
        created_names = {c[1]["name"] for c in created}
        # speckit:task is the canonical type for backlog items; feature label
        # is auto-numbered.
        assert "feature:001-user-auth" in created_names

    def test_reuses_existing_feature_label(self, linear_config):
        mcp = FakeLinearMcp()
        mcp.labels.append({"id": "lbl-existing", "name": "feature:002-user-auth"})
        mcp.issues.append(
            {
                "id": "PMO-100",
                "title": "Legacy ticket",
                "labels": [],
                "project": "speckit-linear-skills",
            }
        )

        run_migrate(
            mcp,
            config=linear_config,
            feature_short_name="user-auth",
            issue_ids=["PMO-100"],
        )

        created = [c[1]["name"] for c in mcp.calls if c[0] == "create_issue_label"]
        assert "feature:002-user-auth" not in created
        # The relabel call must use the EXISTING feature number, not invent 001.
        save_calls = [c for c in mcp.calls if c[0] == "save_issue"]
        assert any(
            "feature:002-user-auth" in (sc[1].get("labels") or []) for sc in save_calls
        )


# ---------------------------------------------------------------------------
# Contract: dual-label application
# ---------------------------------------------------------------------------


class TestAppliesDualLabels:
    def test_each_legacy_issue_gets_both_labels(self, linear_config):
        mcp = FakeLinearMcp()
        mcp.issues.extend(
            [
                {
                    "id": "PMO-100",
                    "title": "Ticket A",
                    "labels": ["legacy"],
                    "project": "speckit-linear-skills",
                },
                {
                    "id": "PMO-101",
                    "title": "Ticket B",
                    "labels": [],
                    "project": "speckit-linear-skills",
                },
            ]
        )

        result = run_migrate(
            mcp,
            config=linear_config,
            feature_short_name="user-auth",
            issue_ids=["PMO-100", "PMO-101"],
        )

        # Each ticket gets BOTH labels added on top of whatever was there.
        for issue_id in ("PMO-100", "PMO-101"):
            issue = next(i for i in mcp.issues if i["id"] == issue_id)
            assert "speckit:task" in issue["labels"]
            assert "feature:001-user-auth" in issue["labels"]

        # Pre-existing labels (e.g., "legacy") are preserved — migrate adds,
        # it doesn't replace.
        ticket_a = next(i for i in mcp.issues if i["id"] == "PMO-100")
        assert "legacy" in ticket_a["labels"]

        assert sorted(result.relabeled_issues) == ["PMO-100", "PMO-101"]

    def test_save_issue_uses_existing_id(self, linear_config):
        """save_issue MUST pass the existing issue id so Linear updates
        in place rather than minting a new ticket."""
        mcp = FakeLinearMcp()
        mcp.issues.append(
            {
                "id": "PMO-100",
                "title": "Ticket",
                "labels": [],
                "project": "speckit-linear-skills",
            }
        )

        run_migrate(
            mcp,
            config=linear_config,
            feature_short_name="user-auth",
            issue_ids=["PMO-100"],
        )

        save_calls = [c for c in mcp.calls if c[0] == "save_issue"]
        assert save_calls, "migrate must call save_issue at least once"
        for tool, payload in save_calls:
            assert payload.get(
                "id"
            ), f"save_issue MUST include the existing id (got {payload!r})"


# ---------------------------------------------------------------------------
# Contract: idempotency (acceptance criterion of T061)
# ---------------------------------------------------------------------------


class TestMigrateIsIdempotent:
    def test_second_run_skips_already_labeled_issues(self, linear_config):
        mcp = FakeLinearMcp()
        mcp.issues.append(
            {
                "id": "PMO-100",
                "title": "Ticket",
                "labels": [],
                "project": "speckit-linear-skills",
            }
        )

        run_migrate(
            mcp,
            config=linear_config,
            feature_short_name="user-auth",
            issue_ids=["PMO-100"],
        )

        mcp.calls.clear()
        second = run_migrate(
            mcp,
            config=linear_config,
            feature_short_name="user-auth",
            issue_ids=["PMO-100"],
        )

        save_calls = [c for c in mcp.calls if c[0] == "save_issue"]
        assert save_calls == [], (
            f"migrate must be idempotent on already-labeled issues; "
            f"saw {save_calls!r}"
        )
        assert second.relabeled_issues == []
        assert "PMO-100" in second.skipped_issues
        assert second.no_op is True


# ---------------------------------------------------------------------------
# Contract: structured return shape
# ---------------------------------------------------------------------------


class TestMigrateResultShape:
    def test_result_dataclass_fields(self, linear_config):
        mcp = FakeLinearMcp()
        result = run_migrate(
            mcp,
            config=linear_config,
            feature_short_name="user-auth",
            issue_ids=[],
        )
        for attr in (
            "relabeled_issues",
            "skipped_issues",
            "feature_label",
            "no_op",
        ):
            assert hasattr(result, attr), f"MigrateResult missing field {attr!r}"
        assert isinstance(result, MigrateResult)
        assert result.no_op is True  # empty input → nothing to do
