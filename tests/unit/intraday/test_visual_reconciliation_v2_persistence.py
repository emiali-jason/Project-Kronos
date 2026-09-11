from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from kronos.intraday.visual_reconciliation_v2 import create_reconciliation_record
from kronos.intraday.visual_reconciliation_v2_persistence import (
    VisualReconciliationPersistenceError,
    VisualReconciliationStore,
)
from tests.unit.intraday.test_visual_reconciliation_v2 import _input


def test_append_restore_replay_and_idempotence(tmp_path):
    store = VisualReconciliationStore(tmp_path.resolve())
    created = datetime(2026, 9, 11, tzinfo=timezone.utc)
    first = create_reconciliation_record(_input(), created_at=created)

    retained, state = store.retain(first)
    assert state == "RECONCILED"
    assert retained == first
    assert store.restore_current("cycle") == first
    assert store.list_records() == (first,)

    replay = create_reconciliation_record(
        _input(), created_at=created + timedelta(minutes=1)
    )
    retained, state = VisualReconciliationStore(tmp_path.resolve()).retain(replay)
    assert state == "ALREADY_RECONCILED"
    assert retained == first
    assert store.list_records() == (first,)


def test_changed_answer_creates_distinct_lineage_without_overwrite(tmp_path):
    store = VisualReconciliationStore(tmp_path.resolve())
    created = datetime(2026, 9, 11, tzinfo=timezone.utc)
    first = create_reconciliation_record(_input(), created_at=created)
    store.retain(first)
    changed_input = replace(
        _input(),
        answer_pack_identity="answer-2",
        answer_source_sha256="c" * 64,
        visual_evidence_identity="visual-2",
    )
    second = create_reconciliation_record(
        changed_input, created_at=created + timedelta(minutes=1)
    )

    retained, state = store.retain(second)
    assert state == "RECONCILED"
    assert retained == second
    assert store.restore_current("cycle") == second
    assert set(store.list_records()) == {first, second}


def test_corrupt_pointer_fails_closed(tmp_path):
    store = VisualReconciliationStore(tmp_path.resolve())
    record = create_reconciliation_record(
        _input(), created_at=datetime(2026, 9, 11, tzinfo=timezone.utc)
    )
    store.retain(record)
    pointer = tmp_path / "current" / "cycle.json"
    pointer.write_bytes(pointer.read_bytes().replace(b"cycle", b"wrong"))
    with pytest.raises(ValueError, match="WO07F_POINTER"):
        store.restore_current("cycle")


def test_immutable_record_conflict_fails_closed(tmp_path):
    store = VisualReconciliationStore(tmp_path.resolve())
    record = create_reconciliation_record(
        _input(), created_at=datetime(2026, 9, 11, tzinfo=timezone.utc)
    )
    store.retain(record)
    path = tmp_path / "records" / f"{record.reconciliation_identity}.json"
    path.write_bytes(path.read_bytes() + b"unexpected")
    with pytest.raises(VisualReconciliationPersistenceError):
        store.retain(record)
