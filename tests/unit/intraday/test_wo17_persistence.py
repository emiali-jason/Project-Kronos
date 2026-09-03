from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json

import pytest

from kronos.application.intraday_wo17 import (
    IntradayWo17Application,
    IntradayWo17RestorationService,
    create_wo17_operation_request,
)
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo16 import Wo16SponsorDecision
from kronos.intraday.wo17_closure import (
    close_wo17_live_position,
    close_wo17_paper_position,
    create_wo17_closure_machine,
    create_wo17_live_exit_attestation,
)
from kronos.intraday.wo17_lifecycle import (
    create_wo17_lifecycle_machine,
    create_wo17_session_end_fact,
    end_wo17_lifecycle_session,
    interrupt_wo17_lifecycle,
)
from kronos.intraday.wo17_persistence import (
    DEFAULT_WO17_ROOT,
    Wo17PersistenceError,
    Wo17RestorationState,
    Wo17Store,
)
from kronos.intraday.wo17_position import create_wo17_position_machine

from .test_wo17_closure import _assessed
from .test_wo17_lifecycle import _active
from .test_wo17_position import _snapshot


def _application(tmp_path):  # type: ignore[no-untyped-def]
    store = Wo17Store((tmp_path / "wo17").resolve())
    return store, IntradayWo17Application(store=store)


def _request(position, *, lifecycle=None, closure=None, exit_attestation=None, at=None):  # type: ignore[no-untyped-def]
    snapshot = position.upstream_snapshot
    return create_wo17_operation_request(
        snapshot=snapshot,
        position=position,
        lifecycle=lifecycle,
        closure=closure,
        live_exit_attestation=exit_attestation,
        requested_at=at or position.last_transition_at + timedelta(minutes=1),
        provenance=("ADR-0027", "WO-17-SLICE-5-TEST"),
    )


def _paper_closed(tmp_path):  # type: ignore[no-untyped-def]
    position, lifecycle, assessment = _assessed(tmp_path)
    result = close_wo17_paper_position(
        create_wo17_closure_machine(position), lifecycle, assessment
    )
    return position, lifecycle, result.current


def _live_closed(tmp_path):  # type: ignore[no-untyped-def]
    _, position = _active(tmp_path, choice=Wo16SponsorDecision.LIVE)
    machine = create_wo17_closure_machine(position)
    evidence = position.position_evidence
    assert evidence is not None
    exited_at = evidence.entry_timestamp + timedelta(hours=1)
    attestation = create_wo17_live_exit_attestation(
        machine=machine,
        actual_exit_price=evidence.entry_price,
        actual_exit_timestamp=exited_at,
        attestation_operation_timestamp=exited_at + timedelta(seconds=1),
        sponsor_operation_identity="SPONSOR-WO17-SLICE-5-EXIT",
        bounded_manual_action_provenance=("SAME-ORIGIN-SPONSOR-ACTION",),
    )
    result = close_wo17_live_position(machine, attestation)
    return position, result.current, attestation


def _fingerprints(root):  # type: ignore[no-untyped-def]
    return {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_evidence_root_is_product_local() -> None:
    assert DEFAULT_WO17_ROOT.parts[-1] == (
        "wo17-position-evidence-active-lifecycle-monitoring-v1"
    )
    assert "intraday-v1" in DEFAULT_WO17_ROOT.parts


def test_empty_and_loaded_paper_and_live_restoration(tmp_path) -> None:
    store, application = _application(tmp_path)
    service = IntradayWo17RestorationService(store=store)
    assert service.restore().state is Wo17RestorationState.NOT_YET_RUN

    _, paper = _active(tmp_path / "paper")
    paper_result = application.execute(_request(paper))
    assert not paper_result.replayed
    restored = service.restore()
    assert restored.state is Wo17RestorationState.LOADED
    assert restored.restored[0].position == paper

    live_store, live_application = _application(tmp_path / "live-store")
    _, live = _active(tmp_path / "live", choice=Wo16SponsorDecision.LIVE)
    live_application.execute(_request(live))
    loaded_live = live_store.restore_current(
        live.upstream_snapshot.lineage.canonical_subject_identity
    )
    assert loaded_live is not None
    assert loaded_live.position == live


def test_armed_active_interrupted_session_ended_and_closed_restore_exactly(tmp_path) -> None:
    cases = []
    _, snapshot = _snapshot(tmp_path / "armed")
    armed = create_wo17_position_machine(snapshot)
    cases.append((armed, None, None))

    _, active = _active(tmp_path / "active")
    lifecycle = create_wo17_lifecycle_machine(active)
    cases.append((active, lifecycle, None))

    interrupted = interrupt_wo17_lifecycle(
        lifecycle, occurred_at=lifecycle.last_transition_at + timedelta(seconds=1)
    ).current
    cases.append((active, interrupted, None))

    lineage = active.upstream_snapshot.lineage
    fact = create_wo17_session_end_fact(
        machine=lifecycle,
        observed_at=lineage.active_window_closes_at,
        source_fact_identity="DOMAIN-008-SLICE-5-END",
        provenance=("DOMAIN-008", "ADR-0027"),
    )
    ended = end_wo17_lifecycle_session(lifecycle, fact).current
    cases.append((active, ended, None))

    closed_position, closed_lifecycle, closed = _paper_closed(tmp_path / "closed")
    cases.append((closed_position, closed_lifecycle, closed))

    for index, (position, life, closure) in enumerate(cases):
        store, application = _application(tmp_path / f"store-{index}")
        request = _request(
            position,
            lifecycle=life,
            closure=closure,
            at=max(
                item
                for item in (
                    position.last_transition_at,
                    None if life is None else life.last_transition_at,
                    None if closure is None else closure.last_transition_at,
                )
                if item is not None
            )
            + timedelta(seconds=1),
        )
        application.execute(request)
        restored = store.restore_current(request.canonical_subject_identity)
        assert restored is not None
        assert restored.position == position
        assert restored.lifecycle == life
        assert restored.closure == closure


def test_live_exit_attestation_and_closure_restore_exactly(tmp_path) -> None:
    position, closure, attestation = _live_closed(tmp_path)
    store, application = _application(tmp_path / "store")
    request = _request(
        position,
        closure=closure,
        exit_attestation=attestation,
        at=attestation.attestation_operation_timestamp,
    )
    application.execute(request)
    restored = store.restore_current(request.canonical_subject_identity)
    assert restored is not None
    assert restored.live_exit_attestation == attestation
    assert restored.closure == closure


def test_active_closure_machine_without_closure_restores_exactly(tmp_path) -> None:
    _, position = _active(tmp_path / "facts")
    closure = create_wo17_closure_machine(position)
    store, application = _application(tmp_path / "store")
    request = _request(position, closure=closure)
    application.execute(request)
    restored = store.restore_current(request.canonical_subject_identity)
    assert restored is not None
    assert restored.closure == closure
    assert restored.pointer.closure_state.value == "ACTIVE"
    assert restored.pointer.closure_identity is None


def test_exact_replay_produces_no_writes(tmp_path) -> None:
    _, position = _active(tmp_path / "facts")
    store, application = _application(tmp_path)
    request = _request(position)
    first = application.execute(request)
    before = _fingerprints(store.root)
    replay = application.execute(request)
    assert replay.replayed
    assert replay.pointer == first.pointer
    assert _fingerprints(store.root) == before


def test_current_history_and_latest_failure_are_separate(tmp_path) -> None:
    _, position = _active(tmp_path / "first")
    store, application = _application(tmp_path)
    first = application.execute(_request(position))
    _, foreign = _active(
        tmp_path / "foreign", direction=SemanticDirection.SHORT
    )
    rejected = _request(foreign)
    with pytest.raises(Exception, match="WO17_EXISTING_NON_CLOSED_POSITION"):
        application.execute(rejected)
    restored = store.restore_current(first.request.canonical_subject_identity)
    assert restored is not None
    assert restored.pointer == first.pointer
    assert restored.latest_failure is not None
    assert restored.latest_failure.reason == "WO17_EXISTING_NON_CLOSED_POSITION"
    assert restored.history == (first.pointer,)


def test_partial_persistence_never_publishes_pointer(tmp_path, monkeypatch) -> None:
    _, position = _active(tmp_path / "facts")
    store, application = _application(tmp_path)

    def fail(_pointer):  # type: ignore[no-untyped-def]
        raise OSError("bounded write failure")

    monkeypatch.setattr(store, "publish_current", fail)
    with pytest.raises(Exception, match="WO17_APPLICATION_FAILURE"):
        application.execute(_request(position))
    assert store.load_current(position.upstream_snapshot.lineage.canonical_subject_identity) is None


def test_tampered_artifact_and_pointer_restore_as_corrupt(tmp_path) -> None:
    _, position = _active(tmp_path / "facts")
    store, application = _application(tmp_path)
    result = application.execute(_request(position))
    alias = next((store.root / "current").glob("CURRENT-WO17-*.json"))
    alias.write_text("{}", encoding="utf-8")
    status = IntradayWo17RestorationService(store=store).restore()
    assert status.state is Wo17RestorationState.CORRUPT
    assert status.failure_reason == "WO17_RESTORATION_FAILED"

    pointer_path = store.root / "current-snapshots" / f"{result.pointer.pointer_identity}.json"
    document = json.loads(pointer_path.read_text(encoding="utf-8"))
    document["artifact_identity"] = "ALTERED"
    pointer_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(Wo17PersistenceError, match="WO17_ARTIFACT_INTEGRITY_INVALID"):
        store.restore_pointer(result.pointer)


def test_path_traversal_and_unsupported_family_are_rejected(tmp_path) -> None:
    store = Wo17Store((tmp_path / "wo17").resolve())
    with pytest.raises(Wo17PersistenceError, match="WO17_ARTIFACT_PATH_INVALID"):
        store.load_current("../../SWING")
    with pytest.raises(Wo17PersistenceError, match="WO17_ARTIFACT_PATH_INVALID"):
        store._path("broker-orders", "WO17-FAKE")


def test_nse_and_mcx_lineage_survive_round_trip(tmp_path) -> None:
    for name, mcx in (("nse", False), ("mcx", True)):
        _, position = _active(tmp_path / name, mcx=mcx)
        store, application = _application(tmp_path / f"store-{name}")
        request = _request(position)
        application.execute(request)
        restored = store.restore_current(request.canonical_subject_identity)
        assert restored is not None
        lineage = restored.snapshot.lineage
        assert (lineage.actual_contract_identity is not None) is mcx
        assert (lineage.roll_lineage_identity is not None) is mcx


def test_restoration_is_read_only(tmp_path) -> None:
    _, position = _active(tmp_path / "facts")
    store, application = _application(tmp_path)
    application.execute(_request(position))
    before = _fingerprints(store.root)
    status = IntradayWo17RestorationService(store=store).restore()
    assert status.state is Wo17RestorationState.LOADED
    assert _fingerprints(store.root) == before


def test_same_identity_different_bytes_is_rejected(tmp_path) -> None:
    _, position = _active(tmp_path / "facts")
    store, _ = _application(tmp_path)
    request = _request(position)
    path = store.retain_request(request)
    path.write_text("foreign", encoding="utf-8")
    with pytest.raises(Wo17PersistenceError, match="WO17_IMMUTABLE_CONFLICT"):
        store.retain_request(request)


def test_request_has_no_economic_or_operational_authority(tmp_path) -> None:
    _, position = _active(tmp_path)
    request = _request(position)
    assert request.quantity == request.fees == "UNAVAILABLE"
    assert request.monetary_pnl == request.realised_r == "UNAVAILABLE"
    assert request.provider_acquisition_authority is False
    assert request.broker_order_authority is False
    assert request.notification_delivery_authority is False
