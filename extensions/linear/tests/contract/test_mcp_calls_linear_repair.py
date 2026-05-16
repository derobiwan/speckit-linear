"""Contract tests for ``/speckit.linear.repair`` (T059).

The repair command reconciles drift between the canonical Linear label set
defined in ``linear-config.yml`` and the live label catalogue in the Linear
workspace. Per the Phase 6 acceptance for T059:

  * Missing canonical ``speckit:<type>`` labels are created via
    ``create_issue_label`` with the canonical color from the config.
  * Existing canonical labels are left alone (no duplicate ``save_*`` calls).
  * Feature labels whose name does not match ``feature:NNN-<short-name>``
    are reported as drift (but never silently rewritten — repair surfaces,
    the user resolves).
  * The command is idempotent: a second run on the just-repaired state
    produces an empty diff.

These tests pin the public surface of
``extensions.linear.scripts.linear_repair`` BEFORE the implementation
lands (Constitution P4 — Test-First, NON-NEGOTIABLE). They MUST fail
until T060 wires up the script.

The MCP boundary is exercised with the same in-memory ``FakeLinearMcp``
shape used by ``test_hook_helpers.py`` — that keeps the contract suite
hermetic and fast, leaving the real HTTP boundary to the VCR-backed
integration suite (T059's ``test_linear_repair_e2e.py``).
"""

from __future__ import annotations

import pytest

# The implementation under test is imported lazily so test collection
# still works when only the tests exist (RED phase).
linear_repair_module = pytest.importorskip(
    "extensions.linear.scripts.linear_repair",
    reason="T060 implementation not yet present — expected during RED phase.",
)
run_repair = linear_repair_module.run
RepairResult = linear_repair_module.RepairResult


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


# ---------------------------------------------------------------------------
# Fake MCP — mirrors the shape used by test_hook_helpers.py
# ---------------------------------------------------------------------------


class FakeLinearMcp:
    """Minimal MCP stand-in that records every call and supports label CRUD."""

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
# Contract: canonical label creation
# ---------------------------------------------------------------------------


class TestCreatesMissingCanonicalLabels:
    """For each ``speckit:<type>`` declared in the config: if absent in
    Linear, the repair command MUST create it via ``create_issue_label``
    using the canonical color from the config."""

    def test_creates_all_canonical_types_on_empty_workspace(self, linear_config):
        mcp = FakeLinearMcp()
        result = run_repair(mcp, config=linear_config)

        created_names = {
            payload["name"]
            for tool, payload in mcp.calls
            if tool == "create_issue_label"
        }
        expected = {f"speckit:{t}" for t in CANONICAL_SPECKIT_TYPES}
        assert created_names == expected
        assert sorted(result.created_labels) == sorted(expected)

    def test_uses_canonical_color_from_config(self, linear_config):
        mcp = FakeLinearMcp()
        run_repair(mcp, config=linear_config)

        for tool, payload in mcp.calls:
            if tool != "create_issue_label":
                continue
            name = payload["name"]
            # Every canonical creation must include a color matching the config.
            assert "color" in payload, f"create_issue_label for {name} missing color"
            speckit_type = name.split(":", 1)[1]
            expected_color = linear_config["labels"]["colors"][speckit_type]
            assert payload["color"] == expected_color

    def test_skips_canonical_types_already_present(self, linear_config):
        mcp = FakeLinearMcp()
        # Seed the workspace with two of the canonical labels.
        mcp.labels.extend(
            [
                {"id": "lbl-a", "name": "speckit:spec", "color": "#10B981"},
                {"id": "lbl-b", "name": "speckit:plan", "color": "#3B82F6"},
            ]
        )
        result = run_repair(mcp, config=linear_config)

        created = [c for c in mcp.calls if c[0] == "create_issue_label"]
        created_names = {c[1]["name"] for c in created}
        # The two seeded labels must NOT be re-created.
        assert "speckit:spec" not in created_names
        assert "speckit:plan" not in created_names
        # All other canonical labels MUST be created.
        assert created_names == {
            f"speckit:{t}" for t in CANONICAL_SPECKIT_TYPES if t not in ("spec", "plan")
        }
        # The result reflects the existing labels.
        assert "speckit:spec" in result.existing_labels
        assert "speckit:plan" in result.existing_labels


# ---------------------------------------------------------------------------
# Contract: feature-label drift detection
# ---------------------------------------------------------------------------


class TestFeatureLabelDriftReporting:
    """Feature labels that don't match ``feature:NNN-<short-name>`` are
    surfaced as drift. Repair never silently rewrites them — the user
    decides what to do."""

    def test_reports_malformed_feature_labels_as_drift(self, linear_config):
        mcp = FakeLinearMcp()
        mcp.labels.extend(
            [
                {"id": "lbl-1", "name": "feature:001-user-auth"},  # compliant
                {"id": "lbl-2", "name": "feature:bad-name"},  # missing NNN
                {"id": "lbl-3", "name": "feature:1-too-short"},  # NN, not NNN
                {"id": "lbl-4", "name": "feature:002-CamelCase"},  # not kebab-case
            ]
        )
        result = run_repair(mcp, config=linear_config)

        drift_names = {d["name"] for d in result.feature_label_drift}
        assert "feature:001-user-auth" not in drift_names
        assert "feature:bad-name" in drift_names
        assert "feature:1-too-short" in drift_names
        assert "feature:002-CamelCase" in drift_names

    def test_does_not_rewrite_drifted_labels(self, linear_config):
        """Repair MUST NOT call ``save_issue_label`` on drift entries.

        Drift is reported, not auto-fixed: the maintainer audits the
        feature graph and decides whether to rename, archive, or delete.
        """
        mcp = FakeLinearMcp()
        mcp.labels.append({"id": "lbl-x", "name": "feature:bad-name"})
        run_repair(mcp, config=linear_config)

        save_calls = [
            c for c in mcp.calls if c[0] in ("save_issue_label", "update_issue_label")
        ]
        assert (
            save_calls == []
        ), f"repair must not mutate drift labels; saw {save_calls!r}"


# ---------------------------------------------------------------------------
# Contract: idempotency (FR-031)
# ---------------------------------------------------------------------------


class TestRepairIsIdempotent:
    def test_second_run_makes_no_new_writes(self, linear_config):
        mcp = FakeLinearMcp()

        first = run_repair(mcp, config=linear_config)
        # First run creates all canonical labels.
        assert len(first.created_labels) == len(CANONICAL_SPECKIT_TYPES)

        # Reset call log but keep the live label state — that's what a
        # second invocation sees.
        mcp.calls.clear()
        second = run_repair(mcp, config=linear_config)

        creates = [c for c in mcp.calls if c[0] == "create_issue_label"]
        assert creates == [], (
            f"repair must be idempotent on already-repaired state; " f"saw {creates!r}"
        )
        assert second.created_labels == []
        assert set(second.existing_labels) == {
            f"speckit:{t}" for t in CANONICAL_SPECKIT_TYPES
        }


# ---------------------------------------------------------------------------
# Contract: structured return shape
# ---------------------------------------------------------------------------


class TestRepairResultShape:
    """``run_repair`` must return a :class:`RepairResult` exposing the
    structured diff the CLI prints, so the command markdown can render
    it deterministically."""

    def test_result_dataclass_fields(self, linear_config):
        mcp = FakeLinearMcp()
        result = run_repair(mcp, config=linear_config)

        # Required attributes — pin the shape so future refactors don't
        # silently drop a field that the command prompt depends on.
        for attr in (
            "created_labels",
            "existing_labels",
            "feature_label_drift",
            "no_op",
        ):
            assert hasattr(result, attr), f"RepairResult missing field {attr!r}"

        # no_op semantics: True iff nothing was created AND no drift detected.
        assert isinstance(result.no_op, bool)
        if result.created_labels:
            assert result.no_op is False
