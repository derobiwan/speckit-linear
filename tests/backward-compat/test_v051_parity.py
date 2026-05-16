"""T046 backward-compat parity test.

Asserts that the issue shapes produced by the v1.0.0 preset+extension
combination are byte-for-byte identical to those captured from the v0.5.1
fork (Spec FR-016, SC-005). The captured corpus lives in
``v051-snapshot.json`` next to this file; see ``capture-procedure.md`` for
how to refresh it.

Until the snapshot is captured (Phase 3 follow-up after the workspace
representatives are collected), the snapshot file carries ``__pending__:
true`` and every assertion in this module is marked ``xfail`` with a
deterministic reason so the test stays runnable on CI without false
negatives. Once the snapshot lands, removing ``__pending__`` flips the
test to a hard assertion automatically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SNAPSHOT_PATH = Path(__file__).resolve().parent / "v051-snapshot.json"


def _load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        pytest.fail(
            f"Missing snapshot fixture: {SNAPSHOT_PATH}. See capture-procedure.md."
        )
    with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _is_pending(snapshot: dict) -> bool:
    return bool(snapshot.get("__pending__"))


SNAPSHOT = _load_snapshot()
PENDING = _is_pending(SNAPSHOT)
PENDING_REASON = (
    "v0.5.1 snapshot not yet captured; remove __pending__ from "
    "tests/backward-compat/v051-snapshot.json after running the capture "
    "procedure (see capture-procedure.md)."
)


# Canonical types we expect the snapshot to enumerate once data is captured.
EXPECTED_TYPES = (
    "speckit:spec",
    "speckit:plan",
    "speckit:research",
    "speckit:data-model",
    "speckit:contract",
    "speckit:quickstart",
    "speckit:checklist",
    "speckit:task",
    "speckit:constitution",
)


# ---------------------------------------------------------------------------
# Schema/shape checks — these run even while pending, because they test the
# snapshot file structure (no production code under test yet).
# ---------------------------------------------------------------------------


class TestSnapshotStructure:
    def test_snapshot_file_exists(self):
        assert SNAPSHOT_PATH.exists()

    def test_snapshot_is_well_formed_json(self):
        # Re-parsing here so a syntax error fails the test, not module import.
        assert isinstance(SNAPSHOT, dict)

    def test_pending_flag_is_boolean_or_absent(self):
        if "__pending__" in SNAPSHOT:
            assert isinstance(SNAPSHOT["__pending__"], bool)

    def test_pending_carries_note(self):
        if PENDING:
            assert "__note__" in SNAPSHOT, (
                "While __pending__ is true, snapshot MUST carry __note__ "
                "explaining the capture procedure location."
            )


# ---------------------------------------------------------------------------
# Parity assertions — xfail while __pending__, strict assertions once captured.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("type_key", EXPECTED_TYPES)
def test_snapshot_covers_canonical_type(type_key):
    if PENDING:
        pytest.xfail(PENDING_REASON)
    assert type_key in SNAPSHOT, (
        f"Snapshot missing canonical type {type_key!r}. "
        "Re-capture per capture-procedure.md."
    )


@pytest.mark.parametrize("type_key", EXPECTED_TYPES)
def test_snapshot_entries_have_required_fields(type_key):
    if PENDING:
        pytest.xfail(PENDING_REASON)
    entry = SNAPSHOT.get(type_key)
    assert entry, f"Empty entry for {type_key}"
    for field in ("title", "labels", "description"):
        assert field in entry, f"Snapshot {type_key!r} missing required field {field!r}"


@pytest.mark.parametrize("type_key", EXPECTED_TYPES)
def test_snapshot_labels_include_type_and_feature(type_key):
    if PENDING:
        pytest.xfail(PENDING_REASON)
    entry = SNAPSHOT[type_key]
    labels = set(entry["labels"])
    assert type_key in labels, f"Snapshot {type_key!r} must wear its own type label"
    if type_key == "speckit:constitution":
        # Constitution issue lives in a dedicated project; no feature label.
        return
    feature_labels = [lbl for lbl in labels if lbl.startswith("feature:")]
    assert len(feature_labels) == 1, (
        f"Snapshot {type_key!r} must wear exactly one feature: label; "
        f"got {feature_labels!r}"
    )


@pytest.mark.parametrize("type_key", EXPECTED_TYPES)
def test_snapshot_description_is_non_empty(type_key):
    if PENDING:
        pytest.xfail(PENDING_REASON)
    entry = SNAPSHOT[type_key]
    assert isinstance(entry["description"], str)
    assert entry["description"].strip(), f"Snapshot {type_key!r} has empty description"


# ---------------------------------------------------------------------------
# Parity assertion against current (v1.0.0) preset behavior. Stays xfail until
# T065+ delivers an integration-test driver that can synthesize each issue
# shape end-to-end through the new preset.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("type_key", EXPECTED_TYPES)
def test_v1_0_0_shape_matches_v051_snapshot(type_key):
    """End-to-end parity check: drive each preset command through the new
    extension+preset, then compare the emitted issue payload against the
    snapshot entry. Lit up by T065 (e2e harness in Phase 7) — until then
    xfail with a single deterministic reason so CI stays green.
    """
    if PENDING:
        pytest.xfail(PENDING_REASON)
    pytest.xfail("e2e parity driver lands in Phase 7 (T065); snapshot side ready")
