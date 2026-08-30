from __future__ import annotations

from datetime import timedelta

import pytest

from kronos.intraday.wo10 import (
    Wo10OperationOutcome,
    Wo10OperationStage,
    create_current_wo10_pointer,
    create_wo10_batch_result,
    create_wo10_operation_provenance,
)
from kronos.intraday.wo10_persistence import Wo10PersistenceError, Wo10Store

from .test_wo10_contracts import PROVENANCE, REQUESTED_AT, _bundle


def _artifacts():  # type: ignore[no-untyped-def]
    _, _, request, snapshot, result = _bundle()
    batch = create_wo10_batch_result(
        request=request,
        results=(result,),
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        provenance=PROVENANCE,
    )
    pointer = create_current_wo10_pointer(request, batch)
    operation = create_wo10_operation_provenance(
        request=request,
        stage=Wo10OperationStage.BATCH_PUBLICATION,
        outcome=Wo10OperationOutcome.COMPLETED,
        started_at=REQUESTED_AT,
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        results=(result,),
        batch=batch,
        provenance=PROVENANCE,
    )
    return request, snapshot, result, batch, pointer, operation


def test_append_only_round_trip_namespace_and_explicit_restoration(tmp_path) -> None:
    store = Wo10Store(tmp_path)
    request, snapshot, result, batch, pointer, operation = _artifacts()

    store.retain_policy(request.policy)
    store.retain_request(request)
    store.retain_evidence_snapshot(snapshot)
    store.retain_result(result)
    store.retain_batch(batch)
    store.retain_operation(operation)
    assert store.load_policy(request.policy.integrity_identity) == request.policy
    assert store.load_request(request.request_identity) == request
    assert store.load_evidence_snapshot(snapshot.snapshot_identity) == snapshot
    assert store.load_result(result.result_identity) == result
    assert store.load_batch(batch.batch_identity) == batch
    assert store.load_operation(operation.operation_identity) == operation
    assert store.load_current(request.market_family) is None

    store.publish_current(pointer)
    restored = store.restore_current(request.market_family)
    assert restored is not None
    assert restored.pointer == pointer
    assert restored.request == request
    assert restored.batch == batch
    assert restored.results == (result,)
    assert restored.evidence_snapshots == (snapshot,)
    assert {item.name for item in tmp_path.iterdir()} == {
        "policies", "requests", "evidence-snapshots", "results", "batches",
        "operations", "current",
    }


def test_same_bytes_are_idempotent_and_conflicting_bytes_fail_closed(tmp_path) -> None:
    store = Wo10Store(tmp_path)
    request, *_ = _artifacts()
    path = store.retain_request(request)
    before = path.read_bytes()
    assert store.retain_request(request) == path
    assert path.read_bytes() == before

    path.write_bytes(b"{}\n")
    with pytest.raises(Wo10PersistenceError, match="WO10_PERSISTENCE_CONFLICT"):
        store.retain_request(request)


@pytest.mark.parametrize("family", ("requests", "evidence-snapshots", "results"))
def test_tamper_and_missing_artifact_detection_are_sanitized(tmp_path, family: str) -> None:
    store = Wo10Store(tmp_path)
    request, snapshot, result, batch, pointer, _ = _artifacts()
    store.retain_request(request)
    store.retain_evidence_snapshot(snapshot)
    store.retain_result(result)
    store.retain_batch(batch)
    store.publish_current(pointer)

    identities = {
        "requests": request.request_identity,
        "evidence-snapshots": snapshot.snapshot_identity,
        "results": result.result_identity,
    }
    path = tmp_path / family / f"{identities[family]}.json"
    payload = path.read_bytes()
    path.write_bytes(payload.replace(b"INTRADAY", b"XNTRADAY", 1))
    with pytest.raises(Wo10PersistenceError, match="WO10_ARTIFACT_INTEGRITY_INVALID"):
        store.restore_current(request.market_family)


def test_pointer_is_not_an_mtime_or_latest_artifact_selector(tmp_path) -> None:
    store = Wo10Store(tmp_path)
    request, snapshot, result, batch, pointer, _ = _artifacts()
    store.retain_request(request)
    store.retain_evidence_snapshot(snapshot)
    store.retain_result(result)
    store.retain_batch(batch)
    stray = tmp_path / "batches" / "ZZZ-LATEST.json"
    stray.write_text("{}")
    assert store.restore_current(request.market_family) is None
    store.publish_current(pointer)
    assert store.restore_current(request.market_family).batch == batch  # type: ignore[union-attr]
