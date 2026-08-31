from __future__ import annotations

import pytest

from kronos.intraday.wo13 import (
    Wo13OperationOutcome, Wo13OperationStage, create_current_wo13_pointer,
    create_wo13_construction_request, create_wo13_operation_provenance,
)
from kronos.intraday.wo13_persistence import Wo13PersistenceError, Wo13Store

from .test_wo13_contracts import _empty_plan, _handoff


def _artifacts(tmp_path):  # type: ignore[no-untyped-def]
    handoff = _handoff(tmp_path)
    request = create_wo13_construction_request(
        handoff=handoff, sponsor_operation_identity="SPONSOR-WO13-SLICE6",
        requested_at=handoff.analysis_boundary, provenance=("ADR-0022", "SLICE6"),
    )
    plan = _empty_plan(request)
    operation = create_wo13_operation_provenance(
        request=request, stage=Wo13OperationStage.POINTER_PUBLICATION,
        outcome=Wo13OperationOutcome.COMPLETED, started_at=request.requested_at,
        completed_at=request.requested_at, trade_plan=plan,
        provenance=("ADR-0022", "POINTER_READY"),
    )
    pointer = create_current_wo13_pointer(
        request=request, trade_plan=plan, operation=operation,
        published_at=request.requested_at,
    )
    return handoff, request, plan, operation, pointer


def test_store_is_append_only_exact_reload_and_same_bytes_idempotent(tmp_path) -> None:
    store = Wo13Store((tmp_path / "wo13").resolve())
    handoff, request, plan, operation, pointer = _artifacts(tmp_path)
    paths = (
        store.retain_handoff(handoff), store.retain_request(request),
        store.retain_trade_plan(plan), store.retain_operation(operation),
    )
    before = tuple(path.read_bytes() for path in paths)
    assert store.retain_request(request) == paths[1]
    assert tuple(path.read_bytes() for path in paths) == before
    store.publish_current(pointer)
    restored = store.restore_current()
    assert restored is not None
    assert (restored.handoff, restored.request, restored.trade_plan, restored.operation) == (
        handoff, request, plan, operation
    )


def test_same_identity_different_bytes_conflicts_without_overwrite(tmp_path) -> None:
    store = Wo13Store((tmp_path / "wo13").resolve())
    _, request, _, _, _ = _artifacts(tmp_path)
    path = store.retain_request(request)
    path.write_text("foreign", encoding="utf-8")
    with pytest.raises(Wo13PersistenceError, match="WO13_IMMUTABLE_CONFLICT"):
        store.retain_request(request)
    assert path.read_text(encoding="utf-8") == "foreign"


def test_absent_pointer_and_corrupt_pointer_are_distinct(tmp_path) -> None:
    store = Wo13Store((tmp_path / "wo13").resolve())
    assert store.restore_current() is None
    _, request, plan, operation, pointer = _artifacts(tmp_path)
    store.retain_handoff(request.handoff)
    store.retain_request(request)
    store.retain_trade_plan(plan)
    store.retain_operation(operation)
    pointer_path = store.publish_current(pointer)
    pointer_path.write_bytes(pointer_path.read_bytes().replace(b"CURRENT-", b"CORRUPT-", 1))
    with pytest.raises(Wo13PersistenceError, match="WO13_ARTIFACT_INTEGRITY_INVALID"):
        store.restore_current()


def test_explicit_identity_path_rejects_traversal_and_plan_corruption(tmp_path) -> None:
    store = Wo13Store((tmp_path / "wo13").resolve())
    _, _, plan, _, _ = _artifacts(tmp_path)
    path = store.retain_trade_plan(plan)
    with pytest.raises(Wo13PersistenceError, match="WO13_ARTIFACT_PATH_INVALID"):
        store.load_trade_plan("../latest")
    path.write_bytes(path.read_bytes()[:-4])
    with pytest.raises(Wo13PersistenceError, match="WO13_ARTIFACT_INTEGRITY_INVALID"):
        store.load_trade_plan(plan.trade_plan_identity)
