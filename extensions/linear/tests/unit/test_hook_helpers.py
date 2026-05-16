"""T027 unit tests: shared hook helpers.

These helpers are imported by every after_* hook script. They wrap the
MCP client with the workflow-specific patterns documented in the spec:
  * Find Active Feature (config → branch → label-scan → ask)
  * Ensure feature label exists, computing next NNN
  * Resolve / create the product project
  * Dual-label resolver: every issue gets exactly
    ``speckit:<type>`` + ``feature:NNN-<name>``
  * Idempotency-key builder for save_issue / save_milestone retries

We test against fakes that stand in for the Linear MCP client; the real
MCP boundary is exercised by the integration tests with recorded VCR
cassettes (T028+ groups).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeLinearMcp:
    """In-memory MCP stand-in.

    Only the call shapes that hook_helpers uses are implemented.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.projects: list[dict] = []
        self.labels: list[dict] = []
        self.issues: list[dict] = []
        self._next_id = 1

    def call(self, tool: str, payload: dict) -> dict:
        self.calls.append((tool, payload))
        if tool == "list_projects":
            name_filter = payload.get("name") or payload.get("query")
            results = [
                p
                for p in self.projects
                if not name_filter or name_filter.lower() in p["name"].lower()
            ]
            return {"data": {"projects": results}}
        if tool == "save_project":
            project_id = payload.get("id") or self._mint_id("prj")
            for existing in self.projects:
                if existing["id"] == project_id:
                    existing.update(payload)
                    return {"data": {"project": existing}}
            project = {"id": project_id, **payload}
            self.projects.append(project)
            return {"data": {"project": project}}
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
# Tests
# ---------------------------------------------------------------------------


class TestEnsureFeatureLabel:
    def test_creates_new_label_when_no_features_exist(self):
        from extensions.linear.scripts.hook_helpers import ensure_feature_label

        mcp = FakeLinearMcp()
        label = ensure_feature_label(mcp, short_name="user-auth")

        assert label["name"] == "feature:001-user-auth"
        assert mcp.labels[0]["name"] == "feature:001-user-auth"

    def test_increments_to_next_unused_number(self):
        from extensions.linear.scripts.hook_helpers import ensure_feature_label

        mcp = FakeLinearMcp()
        mcp.labels.extend(
            [
                {"id": "1", "name": "feature:001-user-auth"},
                {"id": "2", "name": "feature:003-analytics"},
                {"id": "3", "name": "feature:002-payment"},
                {"id": "4", "name": "speckit:spec"},  # not a feature label
            ]
        )

        label = ensure_feature_label(mcp, short_name="search")
        assert label["name"] == "feature:004-search"

    def test_returns_existing_label_when_match_found(self):
        from extensions.linear.scripts.hook_helpers import ensure_feature_label

        mcp = FakeLinearMcp()
        existing = {"id": "lbl-1", "name": "feature:001-user-auth"}
        mcp.labels.append(existing)

        # Idempotency: same short name → same label, no new creation
        label = ensure_feature_label(mcp, short_name="user-auth")
        assert label == existing
        creates = [c for c in mcp.calls if c[0] == "create_issue_label"]
        assert creates == []

    def test_pads_number_to_three_digits(self):
        from extensions.linear.scripts.hook_helpers import ensure_feature_label

        mcp = FakeLinearMcp()
        for n in range(1, 12):
            mcp.labels.append({"id": str(n), "name": f"feature:{n:03d}-feat{n}"})

        label = ensure_feature_label(mcp, short_name="next-one")
        assert label["name"] == "feature:012-next-one"


class TestResolveProductProject:
    def test_returns_existing_project_by_exact_name(self):
        from extensions.linear.scripts.hook_helpers import resolve_product_project

        mcp = FakeLinearMcp()
        existing = {"id": "prj-1", "name": "ACME Product"}
        mcp.projects.append(existing)

        project = resolve_product_project(mcp, name="ACME Product")
        assert project == existing
        # No save_project call when project already exists.
        saves = [c for c in mcp.calls if c[0] == "save_project"]
        assert saves == []

    def test_creates_project_when_missing_and_create_allowed(self):
        from extensions.linear.scripts.hook_helpers import resolve_product_project

        mcp = FakeLinearMcp()
        project = resolve_product_project(
            mcp, name="ACME Product", create_if_missing=True
        )
        assert project["name"] == "ACME Product"
        saves = [c for c in mcp.calls if c[0] == "save_project"]
        assert len(saves) == 1

    def test_raises_when_missing_and_create_disabled(self):
        from extensions.linear.scripts.hook_helpers import (
            ProductProjectNotFoundError,
            resolve_product_project,
        )

        mcp = FakeLinearMcp()
        with pytest.raises(ProductProjectNotFoundError):
            resolve_product_project(mcp, name="ACME Product", create_if_missing=False)

    def test_name_match_is_case_insensitive(self):
        from extensions.linear.scripts.hook_helpers import resolve_product_project

        mcp = FakeLinearMcp()
        existing = {"id": "prj-1", "name": "ACME Product"}
        mcp.projects.append(existing)

        project = resolve_product_project(mcp, name="acme product")
        assert project == existing


class TestDualLabelResolver:
    def test_attaches_both_type_and_feature_labels(self):
        from extensions.linear.scripts.hook_helpers import dual_labels

        labels = dual_labels(speckit_type="spec", feature="001-user-auth")
        assert sorted(labels) == ["feature:001-user-auth", "speckit:spec"]

    def test_rejects_short_name_without_number_prefix(self):
        from extensions.linear.scripts.hook_helpers import (
            FeatureLabelFormatError,
            dual_labels,
        )

        with pytest.raises(FeatureLabelFormatError):
            dual_labels(speckit_type="spec", feature="user-auth")

    def test_rejects_unsupported_speckit_type(self):
        from extensions.linear.scripts.hook_helpers import (
            UnknownSpeckitTypeError,
            dual_labels,
        )

        with pytest.raises(UnknownSpeckitTypeError):
            dual_labels(speckit_type="not-a-type", feature="001-user-auth")

    def test_accepts_all_canonical_types(self):
        from extensions.linear.scripts.hook_helpers import dual_labels

        canonical = (
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
        for t in canonical:
            labels = dual_labels(speckit_type=t, feature="001-x")
            assert f"speckit:{t}" in labels


class TestIdempotencyKey:
    def test_key_is_stable_for_same_inputs(self):
        from extensions.linear.scripts.hook_helpers import idempotency_key

        key1 = idempotency_key("tasks", "001-x", "T001")
        key2 = idempotency_key("tasks", "001-x", "T001")
        assert key1 == key2

    def test_key_differs_when_any_input_changes(self):
        from extensions.linear.scripts.hook_helpers import idempotency_key

        base = idempotency_key("tasks", "001-x", "T001")
        assert base != idempotency_key("plan", "001-x", "T001")
        assert base != idempotency_key("tasks", "002-x", "T001")
        assert base != idempotency_key("tasks", "001-x", "T002")

    def test_key_has_speckit_namespace(self):
        from extensions.linear.scripts.hook_helpers import idempotency_key

        key = idempotency_key("tasks", "001-x", "T001")
        assert key.startswith("speckit:")


class TestFindActiveFeature:
    def test_returns_from_config_when_set(self, tmp_path):
        from extensions.linear.scripts.hook_helpers import find_active_feature

        config = tmp_path / "linear.md"
        config.write_text(
            "# Linear Config\n\n## Active Feature\n\nfeature:003-analytics-dashboard\n",
            encoding="utf-8",
        )
        feature = find_active_feature(
            mcp=FakeLinearMcp(), config_path=config, git_branch=None
        )
        assert feature == "003-analytics-dashboard"

    def test_returns_from_git_branch_when_config_silent(self, tmp_path):
        from extensions.linear.scripts.hook_helpers import find_active_feature

        config = tmp_path / "linear.md"
        config.write_text("# Linear Config\n", encoding="utf-8")
        feature = find_active_feature(
            mcp=FakeLinearMcp(),
            config_path=config,
            git_branch="003-analytics-dashboard",
        )
        assert feature == "003-analytics-dashboard"

    def test_returns_none_when_no_signal(self, tmp_path):
        from extensions.linear.scripts.hook_helpers import find_active_feature

        config = tmp_path / "linear.md"
        config.write_text("", encoding="utf-8")
        result = find_active_feature(
            mcp=FakeLinearMcp(), config_path=config, git_branch=None
        )
        assert result is None

    def test_ignores_branches_that_dont_match_NNN_pattern(self, tmp_path):
        from extensions.linear.scripts.hook_helpers import find_active_feature

        config = tmp_path / "linear.md"
        config.write_text("", encoding="utf-8")
        result = find_active_feature(
            mcp=FakeLinearMcp(), config_path=config, git_branch="main"
        )
        assert result is None
