from __future__ import annotations

from datetime import timedelta

import pytest

from kronos.application.intraday_wo17 import (
    IntradayWo17Application,
    Wo17ApplicationError,
    Wo17BusyOutcome,
    create_wo17_operation_request,
)
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo17_closure import close_wo17_paper_position, create_wo17_closure_machine
from kronos.intraday.wo17_persistence import Wo17Store
from kronos.intraday.wo17_position import create_wo17_position_machine

from .test_wo17_closure import _assessed
from .test_wo17_lifecycle import _active
from .test_wo17_position import _snapshot


def _request(position, *, lifecycle=None, closure=None, at=None):  # type: ignore[no-untyped-def]
    return create_wo17_operation_request(
        snapshot=position.upstream_snapshot,
        position=position,
        lifecycle=lifecycle,
        closure=closure,
        requested_at=at or position.last_transition_at + timedelta(seconds=1),
        provenance=("ADR-0027", "WO-17-SLICE-5-APPLICATION-TEST"),
    )


def _files(root):  # type: ignore[no-untyped-def]
    return tuple(sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file()))


def test_nonblocking_busy_returns_without_writes(tmp_path) -> None:
    _, position = _active(tmp_path / "facts")
    store = Wo17Store((tmp_path / "wo17").resolve())
    application = IntradayWo17Application(store=store)
    application._lock.acquire()
    try:
        result = application.execute(_request(position))
    finally:
        application._lock.release()
    assert type(result) is Wo17BusyOutcome
    assert result.writes_performed == 0
    assert _files(store.root) == ()


def test_subject_cardinality_blocks_foreign_non_closed_successor(tmp_path) -> None:
    _, first = _active(tmp_path / "first")
    _, successor = _active(
        tmp_path / "second", direction=SemanticDirection.SHORT
    )
    store = Wo17Store((tmp_path / "wo17").resolve())
    application = IntradayWo17Application(store=store)
    retained = application.execute(_request(first))
    with pytest.raises(Wo17ApplicationError, match="WO17_EXISTING_NON_CLOSED_POSITION"):
        application.execute(_request(successor))
    restored = store.restore_current(retained.request.canonical_subject_identity)
    assert restored is not None and restored.pointer == retained.pointer


def test_same_snapshot_may_progress_from_armed_to_active(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path / "facts")
    armed = create_wo17_position_machine(snapshot)
    # Recreate active facts over the exact admitted snapshot.
    from kronos.intraday.wo17_position import apply_paper_observation
    from .test_wo17_position import _observation

    entry = snapshot.lineage.entry_reference
    active = apply_paper_observation(armed, _observation(snapshot, str(entry - 1), 1)).current
    active = apply_paper_observation(active, _observation(snapshot, str(entry), 2)).current
    store = Wo17Store((tmp_path / "wo17").resolve())
    application = IntradayWo17Application(store=store)
    first = application.execute(_request(armed))
    second = application.execute(
        _request(active, at=active.last_transition_at + timedelta(seconds=1))
    )
    assert second.pointer.predecessor_pointer_identity == first.pointer.pointer_identity
    assert len(store.restore_current(second.request.canonical_subject_identity).history) == 2  # type: ignore[union-attr]


def test_closed_position_permits_true_successor_and_preserves_history(tmp_path) -> None:
    position, lifecycle, assessment = _assessed(tmp_path / "first")
    closed = close_wo17_paper_position(
        create_wo17_closure_machine(position), lifecycle, assessment
    ).current
    store = Wo17Store((tmp_path / "wo17").resolve())
    application = IntradayWo17Application(store=store)
    first = application.execute(
        _request(
            position,
            lifecycle=lifecycle,
            closure=closed,
            at=closed.last_transition_at + timedelta(seconds=1),
        )
    )
    _, successor = _active(
        tmp_path / "successor", direction=SemanticDirection.SHORT
    )
    second = application.execute(
        _request(successor, at=max(successor.last_transition_at, first.pointer.published_at) + timedelta(seconds=1))
    )
    assert second.pointer.predecessor_pointer_identity == first.pointer.pointer_identity
    assert second.pointer.successor_lineage_identity is not None
    restored = store.restore_current(second.request.canonical_subject_identity)
    assert restored is not None and len(restored.history) == 2
    assert restored.successor is not None
    assert restored.successor.predecessor_closure_identity == (
        first.pointer.closure_identity
    )
    assert restored.successor.automatic_contract_migration is False


def test_closed_position_cannot_be_rewritten(tmp_path) -> None:
    position, lifecycle, assessment = _assessed(tmp_path)
    closed = close_wo17_paper_position(
        create_wo17_closure_machine(position), lifecycle, assessment
    ).current
    store = Wo17Store((tmp_path / "wo17").resolve())
    application = IntradayWo17Application(store=store)
    application.execute(
        _request(position, lifecycle=lifecycle, closure=closed, at=closed.last_transition_at + timedelta(seconds=1))
    )
    with pytest.raises(Wo17ApplicationError, match="WO17_CLOSED_POSITION_FINAL"):
        application.execute(
            _request(position, lifecycle=lifecycle, at=closed.last_transition_at + timedelta(seconds=2))
        )


def test_stale_operation_fails_closed(tmp_path) -> None:
    _, position = _active(tmp_path)
    store = Wo17Store((tmp_path / "wo17").resolve())
    application = IntradayWo17Application(store=store)
    first = application.execute(_request(position))
    with pytest.raises(Wo17ApplicationError, match="WO17_STALE_OPERATION"):
        application.execute(
            _request(position, at=first.pointer.published_at - timedelta(seconds=1))
        )


def test_application_does_not_recalculate_slice_engines(tmp_path) -> None:
    _, position = _active(tmp_path)
    store = Wo17Store((tmp_path / "wo17").resolve())
    request = _request(position)
    result = IntradayWo17Application(store=store).execute(request)
    assert result.request.position is position
    assert result.pointer.position_state is position.state
    assert result.pointer.provider_acquisition_authority is False
    assert result.pointer.broker_order_authority is False
    assert result.pointer.notification_delivery_authority is False
    assert result.pointer.economics_authority is False
