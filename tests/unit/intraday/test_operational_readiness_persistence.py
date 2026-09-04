from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json

import pytest

from kronos.intraday.operational_readiness import (
    WoBClassificationBasis,
    WoBSourceBoundary,
    create_operational_review_snapshot,
    create_review_item,
    create_source_artifact_reference,
)
from kronos.intraday.operational_readiness_persistence import (
    DEFAULT_WO_B_ROOT,
    WoBFailureStage,
    WoBPersistenceError,
    WoBStore,
    create_wo_b_failure,
)
import kronos.intraday.operational_readiness_persistence as persistence_module
from kronos.intraday.universe import IntradayMarketFamily

from .test_operational_readiness import BOUNDARY


def _snapshot(*, boundary=BOUNDARY, candidate="INTRADAY-CANDIDATE-1"):  # type: ignore[no-untyped-def]
    reference = create_source_artifact_reference(
        source_boundary=WoBSourceBoundary.PROBABLES,
        artifact_identity=f"PROBABLE-{candidate}-{boundary.isoformat()}",
        artifact_schema_identity="KRONOS-INTRADAY-PROBABLE-V2",
        artifact_schema_version="2.0.0",
        source_policy_identity="KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V2",
        source_policy_version="2.1.0",
        source_integrity_identity=f"INTEGRITY-PROBABLE-{candidate}",
        candidate_identity=candidate,
        analysis_run_identity="INTRADAY-PROBABLES-RUN-1",
        canonical_instrument_identity="NSE-INSTRUMENT-1",
        active_contract_identity=None,
        exact_source_state="SHORT_PROBABLE",
        exact_source_reason=None,
        bounded_diagnostic=None,
        observed_at=boundary - timedelta(seconds=1),
        current_at_review_boundary=True,
        superseded=False,
        currentness_required=True,
    )
    item = create_review_item(
        source_boundary=reference.source_boundary,
        classification_basis=WoBClassificationBasis.CURRENT_VALID_SOURCE,
        source_reference=reference,
        next_governed_stage="ANALYTICAL_PROMOTION",
    )
    return create_operational_review_snapshot(
        review_boundary=boundary,
        created_at=boundary + timedelta(seconds=1),
        candidate_identity=candidate,
        opportunity_identity=f"OPPORTUNITY-{candidate}",
        analysis_run_lineage=("INTRADAY-DISCOVERY-RUN-1", "INTRADAY-PROBABLES-RUN-1"),
        canonical_subject_identity="NSE-EQ-TEST",
        market_family=IntradayMarketFamily.NSE_EQUITY,
        canonical_instrument_identity="NSE-INSTRUMENT-1",
        active_contract_identity=None,
        source_artifact_references=(reference,),
        review_items=(item,),
        provenance=("ADR-0029", "WO-B1-PERSISTENCE-TEST"),
    )


def _fingerprints(root):  # type: ignore[no-untyped-def]
    return {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_default_namespace_is_intraday_product_local() -> None:
    assert DEFAULT_WO_B_ROOT.parts[-1] == "wo-b-operational-readiness-review-v1"
    assert "intraday-v1" in DEFAULT_WO_B_ROOT.parts


def test_immutable_snapshot_round_trip_and_exact_replay_are_idempotent(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    snapshot = _snapshot()
    path = store.retain_snapshot(snapshot)
    before = _fingerprints(store.root)
    assert store.replay_snapshot(snapshot) == snapshot
    assert store.load_snapshot(snapshot.review_snapshot_identity) == snapshot
    assert _fingerprints(store.root) == before
    assert path.is_file()


def test_conflicting_bytes_and_tampered_artifacts_fail_closed(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    snapshot = _snapshot()
    path = store.retain_snapshot(snapshot)
    path.write_text("foreign", encoding="utf-8")
    with pytest.raises(WoBPersistenceError, match="WO_B_IMMUTABLE_CONFLICT"):
        store.retain_snapshot(snapshot)
    with pytest.raises(WoBPersistenceError, match="WO_B_ARTIFACT_INTEGRITY_INVALID"):
        store.load_snapshot(snapshot.review_snapshot_identity)


def test_first_and_newer_current_projection_preserve_immutable_history(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    first = _snapshot()
    first_pointer = store.publish_current(first)
    second = _snapshot(boundary=BOUNDARY + timedelta(minutes=5))
    second_pointer = store.publish_current(second)
    restored = store.restore_current(first.candidate_identity)
    assert restored.pointer == second_pointer
    assert restored.snapshot == second
    assert store.load_snapshot(first.review_snapshot_identity) == first
    assert first_pointer.pointer_identity != second_pointer.pointer_identity


def test_exact_current_replay_performs_no_writes(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    snapshot = _snapshot()
    pointer = store.publish_current(snapshot)
    before = _fingerprints(store.root)
    assert store.publish_current(snapshot) == pointer
    assert _fingerprints(store.root) == before


def test_stale_or_conflicting_current_never_replaces_valid_pointer(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    current = _snapshot(boundary=BOUNDARY + timedelta(minutes=5))
    pointer = store.publish_current(current)
    with pytest.raises(WoBPersistenceError, match="WO_B_CURRENT_SNAPSHOT_NOT_NEWER"):
        store.publish_current(_snapshot(boundary=BOUNDARY))
    assert store.load_current(current.candidate_identity) == pointer


def test_pointer_publication_failure_preserves_previous_current(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    store = WoBStore((tmp_path / "wo-b").resolve())
    current = _snapshot()
    pointer = store.publish_current(current)
    original_replace = persistence_module._replace_atomic
    calls = 0

    def fail_once(path, encoded):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("bounded alias failure")
        return original_replace(path, encoded)

    monkeypatch.setattr(persistence_module, "_replace_atomic", fail_once)
    with pytest.raises(OSError, match="bounded alias failure"):
        store.publish_current(_snapshot(boundary=BOUNDARY + timedelta(minutes=5)))
    assert store.load_current(current.candidate_identity) == pointer


def test_latest_failure_is_bounded_and_preserves_current(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    snapshot = _snapshot()
    pointer = store.publish_current(snapshot)
    failure = create_wo_b_failure(
        candidate_identity=snapshot.candidate_identity,
        analysis_run_identity=snapshot.analysis_run_lineage[-1],
        stage=WoBFailureStage.SOURCE_BINDING,
        reason="WO_B_SOURCE_INTEGRITY_MISMATCH",
        failed_at=BOUNDARY + timedelta(minutes=1),
        source_identities=(snapshot.source_artifact_references[0].artifact_identity,),
    )
    store.publish_latest_failure(failure)
    restored = store.restore_current(snapshot.candidate_identity)
    assert restored.pointer == pointer
    assert restored.snapshot == snapshot
    assert restored.latest_failure == failure
    assert not (store.root / "snapshots" / f"{failure.failure_identity}.json").exists()


def test_failure_without_snapshot_does_not_fabricate_current(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    failure = create_wo_b_failure(
        candidate_identity="INTRADAY-CANDIDATE-1",
        analysis_run_identity=None,
        stage=WoBFailureStage.SNAPSHOT_VALIDATION,
        reason="WO_B_REQUIRED_IDENTITY_MISSING",
        failed_at=BOUNDARY,
    )
    store.publish_latest_failure(failure)
    assert store.load_current(failure.candidate_identity) is None
    assert store.load_latest_failure(failure.candidate_identity) == failure
    assert not (store.root / "snapshots").exists()
    with pytest.raises(Exception, match="WO_B_FAILURE_INVALID"):
        create_wo_b_failure(
            candidate_identity="INTRADAY-CANDIDATE-1",
            analysis_run_identity=None,
            stage=WoBFailureStage.SNAPSHOT_VALIDATION,
            reason="raw /private/path exception",
            failed_at=BOUNDARY,
        )


def test_restoration_is_inert_and_deterministic(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    snapshot = _snapshot()
    store.publish_current(snapshot)
    before = _fingerprints(store.root)
    first = store.restore_current(snapshot.candidate_identity)
    second = store.restore_current(snapshot.candidate_identity)
    assert first == second
    assert _fingerprints(store.root) == before


def test_corrupt_current_pointer_and_foreign_target_fail_closed(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    snapshot = _snapshot()
    store.publish_current(snapshot)
    alias = store._current_path(snapshot.candidate_identity)
    document = json.loads(alias.read_text(encoding="utf-8"))
    document["document_integrity"] = "tampered"
    alias.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(WoBPersistenceError, match="WO_B_ARTIFACT_INTEGRITY_INVALID"):
        store.restore_current(snapshot.candidate_identity)

    foreign_store = WoBStore((tmp_path / "foreign").resolve())
    foreign = _snapshot(candidate="INTRADAY-CANDIDATE-FOREIGN")
    foreign_store.publish_current(foreign)
    foreign_alias = foreign_store._current_path(foreign.candidate_identity)
    target_alias = foreign_store._current_path("INTRADAY-CANDIDATE-1")
    target_alias.parent.mkdir(parents=True, exist_ok=True)
    target_alias.write_bytes(foreign_alias.read_bytes())
    with pytest.raises(WoBPersistenceError, match="WO_B_CURRENT_POINTER_INTEGRITY_INVALID"):
        foreign_store.restore_current("INTRADAY-CANDIDATE-1")


def test_path_traversal_and_unknown_artifact_family_are_rejected(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    with pytest.raises(WoBPersistenceError, match="WO_B_ARTIFACT_PATH_INVALID"):
        store.load_current("../../SWING")
    with pytest.raises(WoBPersistenceError, match="WO_B_ARTIFACT_PATH_INVALID"):
        store._path("broker-orders", "WO-B-FAKE")


def test_snapshot_integrity_or_pointer_target_cannot_be_rewritten(tmp_path) -> None:
    store = WoBStore((tmp_path / "wo-b").resolve())
    snapshot = _snapshot()
    pointer = store.publish_current(snapshot)
    with pytest.raises(Exception, match="WO_B_REVIEW_SNAPSHOT_INVALID"):
        replace(snapshot, snapshot_integrity_hash="0" * 64)
    with pytest.raises(Exception, match="WO_B_CURRENT_POINTER_INVALID"):
        replace(pointer, review_snapshot_identity="FOREIGN-SNAPSHOT")
