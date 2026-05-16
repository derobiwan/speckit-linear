"""Contract tests for ``/speckit.linear.baseline`` (T063).

The baseline command analyzes an existing source code directory and
produces a ``[SPEC]`` issue describing the discovered features. Per the
Phase 6 acceptance for T063:

  * Source code under a target directory is scanned (no shell-out, no
    network).
  * Discovered features become bullet items in the generated ``[SPEC]``
    description body.
  * A single ``save_issue`` call persists the ``[SPEC]`` with the dual
    ``speckit:spec`` + ``feature:NNN-<short>`` labels.
  * Re-running on the same source produces an idempotent update —
    ``save_issue`` is called with the existing id, not a new one.

These tests pin the public surface of
``extensions.linear.scripts.linear_baseline`` BEFORE the implementation
lands (Constitution P4 — Test-First, NON-NEGOTIABLE).
"""

from __future__ import annotations

from pathlib import Path

import pytest

linear_baseline_module = pytest.importorskip(
    "extensions.linear.scripts.linear_baseline",
    reason="T064 implementation not yet present — expected during RED phase.",
)
run_baseline = linear_baseline_module.run
BaselineResult = linear_baseline_module.BaselineResult


# ---------------------------------------------------------------------------
# Fake MCP
# ---------------------------------------------------------------------------


class FakeLinearMcp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.labels: list[dict] = []
        self.issues: list[dict] = []
        self.projects: list[dict] = []
        self._next_id = 0

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
            results = [
                i
                for i in self.issues
                if not label_filter or label_filter in i.get("labels", [])
            ]
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
# Source corpus fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_corpus(tmp_path: Path) -> Path:
    """A small but realistic source tree the baseline scanner can recognize."""
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "__init__.py").write_text(
        '"""User authentication module."""\n',
        encoding="utf-8",
    )
    (tmp_path / "src" / "auth" / "login.py").write_text(
        "def login(user, password):\n    pass\n",
        encoding="utf-8",
    )

    (tmp_path / "src" / "payments").mkdir(parents=True)
    (tmp_path / "src" / "payments" / "__init__.py").write_text(
        '"""Payment processing module."""\n',
        encoding="utf-8",
    )
    (tmp_path / "src" / "payments" / "charge.py").write_text(
        "def charge(amount):\n    pass\n",
        encoding="utf-8",
    )

    # A non-source file that must NOT show up as a feature.
    (tmp_path / "README.md").write_text("# Sample Project\n", encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# Contract: feature discovery
# ---------------------------------------------------------------------------


class TestFeatureDiscovery:
    def test_discovers_top_level_source_modules_as_features(
        self, sample_corpus, linear_config
    ):
        mcp = FakeLinearMcp()
        result = run_baseline(
            mcp,
            config=linear_config,
            source_dir=sample_corpus,
            feature_short_name="discovered-architecture",
        )

        feature_names = {f["name"] for f in result.discovered_features}
        assert "auth" in feature_names
        assert "payments" in feature_names

    def test_excludes_non_source_files(self, sample_corpus, linear_config):
        mcp = FakeLinearMcp()
        result = run_baseline(
            mcp,
            config=linear_config,
            source_dir=sample_corpus,
            feature_short_name="discovered-architecture",
        )
        feature_names = {f["name"] for f in result.discovered_features}
        assert "README.md" not in feature_names
        # No phantom feature for the project root itself.
        assert "src" not in feature_names

    def test_empty_directory_yields_empty_feature_list(self, tmp_path, linear_config):
        mcp = FakeLinearMcp()
        result = run_baseline(
            mcp,
            config=linear_config,
            source_dir=tmp_path,
            feature_short_name="empty",
        )
        assert result.discovered_features == []


# ---------------------------------------------------------------------------
# Contract: SPEC issue persistence
# ---------------------------------------------------------------------------


class TestSpecIssuePersistence:
    def test_persists_a_single_spec_issue(self, sample_corpus, linear_config):
        mcp = FakeLinearMcp()
        result = run_baseline(
            mcp,
            config=linear_config,
            source_dir=sample_corpus,
            feature_short_name="discovered-architecture",
        )

        save_calls = [c for c in mcp.calls if c[0] == "save_issue"]
        assert (
            len(save_calls) == 1
        ), f"baseline must persist exactly one [SPEC] issue; saw {save_calls!r}"
        payload = save_calls[0][1]
        assert payload["title"].startswith("[SPEC]")
        assert "discovered-architecture" in payload["title"].lower()

        # Dual labels MUST be present.
        labels = payload.get("labels") or []
        assert "speckit:spec" in labels
        assert any(
            label.startswith("feature:") and label.endswith("-discovered-architecture")
            for label in labels
        )

        assert result.spec_issue_id is not None

    def test_spec_body_mentions_each_discovered_feature(
        self, sample_corpus, linear_config
    ):
        mcp = FakeLinearMcp()
        run_baseline(
            mcp,
            config=linear_config,
            source_dir=sample_corpus,
            feature_short_name="discovered-architecture",
        )

        save_calls = [c for c in mcp.calls if c[0] == "save_issue"]
        body = save_calls[0][1].get("description", "")
        assert "auth" in body
        assert "payments" in body


# ---------------------------------------------------------------------------
# Contract: idempotency
# ---------------------------------------------------------------------------


class TestBaselineIsIdempotent:
    def test_rerun_updates_existing_spec_issue(self, sample_corpus, linear_config):
        mcp = FakeLinearMcp()

        first = run_baseline(
            mcp,
            config=linear_config,
            source_dir=sample_corpus,
            feature_short_name="discovered-architecture",
        )
        first_id = first.spec_issue_id

        mcp.calls.clear()
        second = run_baseline(
            mcp,
            config=linear_config,
            source_dir=sample_corpus,
            feature_short_name="discovered-architecture",
        )

        saves = [c for c in mcp.calls if c[0] == "save_issue"]
        # save_issue is allowed (the body may change as features evolve) but
        # MUST target the existing issue id, not create a new one.
        for tool, payload in saves:
            assert payload.get("id") == first_id, (
                f"baseline re-run must update spec in place; "
                f"saw payload id={payload.get('id')!r}, expected {first_id!r}"
            )
        assert second.spec_issue_id == first_id


# ---------------------------------------------------------------------------
# Contract: structured return shape
# ---------------------------------------------------------------------------


class TestBaselineResultShape:
    def test_result_dataclass_fields(self, sample_corpus, linear_config):
        mcp = FakeLinearMcp()
        result = run_baseline(
            mcp,
            config=linear_config,
            source_dir=sample_corpus,
            feature_short_name="discovered-architecture",
        )
        for attr in (
            "discovered_features",
            "spec_issue_id",
            "feature_label",
            "no_op",
        ):
            assert hasattr(result, attr), f"BaselineResult missing field {attr!r}"
        assert isinstance(result, BaselineResult)
