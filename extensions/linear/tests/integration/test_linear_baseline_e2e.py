"""Integration tests for ``/speckit.linear.baseline`` (T063, e2e).

Exercises the full baseline flow through an in-memory MCP fake plus a
realistic source corpus on the filesystem.

Acceptance criterion from PMO-140 (T063): analyzing a code directory
produces a ``[SPEC]`` issue describing the discovered features.
"""

from __future__ import annotations

from pathlib import Path

import pytest

linear_baseline_module = pytest.importorskip(
    "extensions.linear.scripts.linear_baseline",
    reason="T064 implementation not yet present — expected during RED phase.",
)
run_baseline = linear_baseline_module.run


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
            return {"data": {"projects": list(self.projects)}}
        if tool == "save_project":
            project_id = payload.get("id") or self._mint_id("prj")
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
            return {
                "data": {
                    "issues": [
                        i
                        for i in self.issues
                        if not label_filter or label_filter in i.get("labels", [])
                    ]
                }
            }
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


@pytest.fixture()
def realistic_corpus(tmp_path: Path) -> Path:
    """A multi-feature source tree the baseline analyzer can walk."""
    for feature in ("auth", "payments", "notifications"):
        pkg = tmp_path / "src" / feature
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text(
            f'"""{feature} feature module."""\n', encoding="utf-8"
        )
        (pkg / "api.py").write_text("def handler():\n    pass\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Scenario: code → [SPEC] issue with feature list in body
# ---------------------------------------------------------------------------


def test_directory_scan_produces_spec_issue_with_feature_list(
    realistic_corpus, linear_config
):
    mcp = FakeLinearMcp()
    result = run_baseline(
        mcp,
        config=linear_config,
        source_dir=realistic_corpus,
        feature_short_name="reverse-engineered",
    )

    # Three discovered features.
    feature_names = {f["name"] for f in result.discovered_features}
    assert feature_names == {"auth", "payments", "notifications"}

    # Exactly one [SPEC] issue persisted with dual labels.
    save_calls = [c for c in mcp.calls if c[0] == "save_issue"]
    assert len(save_calls) == 1
    payload = save_calls[0][1]
    assert payload["title"].startswith("[SPEC]")
    labels = payload.get("labels") or []
    assert "speckit:spec" in labels
    assert any(
        lbl.startswith("feature:") and lbl.endswith("-reverse-engineered")
        for lbl in labels
    )

    body = payload.get("description", "")
    for feature in ("auth", "payments", "notifications"):
        assert feature in body


# ---------------------------------------------------------------------------
# Scenario: idempotency on re-run with same source
# ---------------------------------------------------------------------------


def test_baseline_rerun_updates_in_place(realistic_corpus, linear_config):
    mcp = FakeLinearMcp()
    first = run_baseline(
        mcp,
        config=linear_config,
        source_dir=realistic_corpus,
        feature_short_name="reverse-engineered",
    )

    mcp.calls.clear()
    second = run_baseline(
        mcp,
        config=linear_config,
        source_dir=realistic_corpus,
        feature_short_name="reverse-engineered",
    )

    saves = [c for c in mcp.calls if c[0] == "save_issue"]
    for _, payload in saves:
        assert payload.get("id") == first.spec_issue_id
    assert second.spec_issue_id == first.spec_issue_id
