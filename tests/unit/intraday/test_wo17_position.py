from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_wo16 import IntradayWo16PersistenceApplication
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo16 import Wo16SponsorDecision
from kronos.intraday.wo16_persistence import Wo16Store
from kronos.intraday.wo17_adapters import bind_wo17_upstream
from kronos.intraday.wo17_position import (
    Wo17EntryContinuity,
    Wo17PositionEvent,
    Wo17PositionFailure,
    Wo17PositionRejected,
    Wo17PositionState,
    apply_live_entry_attestation,
    apply_paper_observation,
    apply_pre_entry_invalidation,
    create_wo17_entry_observation,
    create_wo17_live_entry_attestation,
    create_wo17_position_machine,
    create_wo17_pre_entry_invalidation_fact,
    expire_entry_window,
    interrupt_paper_entry_sequence,
    recover_paper_entry_sequence,
)

from .test_wo16_application import _request
from .test_wo16_contracts import _chain


IST = ZoneInfo("Asia/Kolkata")


def _snapshot(  # type: ignore[no-untyped-def]
    tmp_path,
    *,
    choice=Wo16SponsorDecision.PAPER,
    direction=SemanticDirection.LONG,
    mcx=False,
):
    chain = _chain(tmp_path / "chain", direction=direction, mcx=mcx)
    store = Wo16Store((tmp_path / "wo16").resolve())
    IntradayWo16PersistenceApplication(store=store).execute(_request(chain, choice))
    restored = store.restore_current(chain["plan"].canonical_subject_identity)
    assert restored is not None
    snapshot = bind_wo17_upstream(
        current_pointer=restored.pointer,
        snapshot=restored.snapshot,
        decision=restored.decision,
        admission=restored.admission,
        bound_at=chain["observed_at"] + timedelta(seconds=4),
    )
    return chain, snapshot


def _observation(  # type: ignore[no-untyped-def]
    snapshot,
    price,
    sequence,
    *,
    observed_at=None,
    sequence_identity=None,
):
    return create_wo17_entry_observation(
        snapshot=snapshot,
        provider_identity="DOMAIN-006-KITE-READ-ONLY",
        observed_price=Decimal(price),
        observed_at=observed_at or snapshot.bound_at + timedelta(seconds=sequence),
        source_sequence_identity=sequence_identity or f"KITE-TICK-SEQUENCE-{sequence}",
        source_sequence=sequence,
        provenance=("ADR-0027", "WO-17-SLICE-2-TEST"),
    )


def _attestation(snapshot, *, entry_at=None, attested_at=None):  # type: ignore[no-untyped-def]
    entry_at = entry_at or snapshot.bound_at + timedelta(seconds=1)
    attested_at = attested_at or entry_at + timedelta(seconds=1)
    return create_wo17_live_entry_attestation(
        snapshot=snapshot,
        actual_entry_price=snapshot.lineage.entry_reference,
        actual_entry_timestamp=entry_at,
        attestation_operation_timestamp=attested_at,
        sponsor_operation_identity="SPONSOR-WO17-LIVE-ENTRY-TEST",
        bounded_manual_action_provenance=("SAME-ORIGIN-SPONSOR-ACTION",),
    )


def _cross(machine, *, first="99", second="100", first_sequence=1):  # type: ignore[no-untyped-def]
    first_result = apply_paper_observation(
        machine, _observation(machine.upstream_snapshot, first, first_sequence)
    )
    return apply_paper_observation(
        first_result.current,
        _observation(machine.upstream_snapshot, second, first_sequence + 1),
    )


def test_paper_and_live_initial_states_are_decision_specific(tmp_path) -> None:
    _, paper = _snapshot(tmp_path / "paper")
    _, live = _snapshot(tmp_path / "live", choice=Wo16SponsorDecision.LIVE)
    paper_machine = create_wo17_position_machine(paper)
    live_machine = create_wo17_position_machine(live)
    assert paper_machine.state is Wo17PositionState.PAPER_ARMED
    assert paper_machine.continuity is Wo17EntryContinuity.AVAILABLE
    assert live_machine.state is Wo17PositionState.LIVE_AWAITING_SPONSOR_ENTRY_EVIDENCE
    assert live_machine.continuity is Wo17EntryContinuity.NOT_APPLICABLE
    assert paper_machine.position_evidence is live_machine.position_evidence is None


@pytest.mark.parametrize(
    ("direction", "first_delta", "second_delta"),
    (
        (SemanticDirection.LONG, Decimal("-0.05"), Decimal("0")),
        (SemanticDirection.SHORT, Decimal("0.05"), Decimal("0")),
    ),
)
def test_long_and_short_inclusive_crossings_create_paper_position(
    tmp_path, direction, first_delta, second_delta
) -> None:
    _, snapshot = _snapshot(tmp_path, direction=direction)
    entry = snapshot.lineage.entry_reference
    machine = create_wo17_position_machine(snapshot)
    first = apply_paper_observation(machine, _observation(snapshot, str(entry + first_delta), 1))
    assert first.event is Wo17PositionEvent.PAPER_BASELINE_OBSERVED
    assert first.current.position_evidence is None
    crossed = apply_paper_observation(
        first.current, _observation(snapshot, str(entry + second_delta), 2)
    )
    assert crossed.event is Wo17PositionEvent.PAPER_ENTRY_OBSERVED
    assert crossed.current.state is Wo17PositionState.PAPER_ACTIVE
    evidence = crossed.current.position_evidence
    assert evidence is not None
    assert evidence.entry_price == entry
    assert evidence.source_sequence == 2
    assert evidence.upstream_lineage_identity == snapshot.lineage.lineage_identity
    assert evidence.evidence_role == "MODEL_POSITION_EVIDENCE"


def test_first_observation_at_or_beyond_entry_is_baseline_only(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path)
    result = apply_paper_observation(
        create_wo17_position_machine(snapshot),
        _observation(snapshot, str(snapshot.lineage.entry_reference), 1),
    )
    assert result.current.state is Wo17PositionState.PAPER_ARMED
    assert result.current.position_evidence is None


def test_paper_cutoff_is_strict_and_market_specific(tmp_path) -> None:
    for mcx, hour in ((False, 15), (True, 23)):
        _, snapshot = _snapshot(tmp_path / str(mcx), mcx=mcx)
        entry = snapshot.lineage.entry_reference
        before = datetime.combine(snapshot.lineage.trading_date, datetime.min.time(), tzinfo=IST).replace(
            hour=hour - 1, minute=59, second=58
        )
        machine = create_wo17_position_machine(snapshot)
        first = apply_paper_observation(
            machine, _observation(snapshot, str(entry - Decimal("0.05")), 1, observed_at=before)
        )
        accepted = apply_paper_observation(
            first.current,
            _observation(snapshot, str(entry), 2, observed_at=before + timedelta(seconds=1)),
        )
        assert accepted.current.state is Wo17PositionState.PAPER_ACTIVE

        for seconds in (0, 1):
            at_or_after = before + timedelta(seconds=2 + seconds)
            fresh = create_wo17_position_machine(snapshot)
            with pytest.raises(Wo17PositionRejected) as found:
                apply_paper_observation(
                    fresh, _observation(snapshot, str(entry), 10 + seconds, observed_at=at_or_after)
                )
            assert found.value.failure is Wo17PositionFailure.ENTRY_CUTOFF_REACHED


def test_live_requires_both_entry_and_attestation_strictly_before_cutoff(tmp_path) -> None:
    for mcx, hour in ((False, 15), (True, 23)):
        _, snapshot = _snapshot(
            tmp_path / str(mcx), choice=Wo16SponsorDecision.LIVE, mcx=mcx
        )
        cutoff = datetime.combine(
            snapshot.lineage.trading_date, datetime.min.time(), tzinfo=IST
        ).replace(hour=hour)
        valid = apply_live_entry_attestation(
            create_wo17_position_machine(snapshot),
            _attestation(
                snapshot,
                entry_at=cutoff - timedelta(seconds=2),
                attested_at=cutoff - timedelta(seconds=1),
            ),
        )
        assert valid.current.state is Wo17PositionState.LIVE_ACTIVE
        assert valid.event is Wo17PositionEvent.LIVE_ENTRY_ATTESTED
        assert valid.current.position_evidence is not None
        assert valid.current.position_evidence.entry_timestamp == cutoff - timedelta(
            seconds=2
        )

        for entry_at, attested_at in (
            (cutoff, cutoff),
            (cutoff - timedelta(seconds=1), cutoff),
            (cutoff + timedelta(seconds=1), cutoff + timedelta(seconds=2)),
        ):
            with pytest.raises(Wo17PositionRejected) as found:
                apply_live_entry_attestation(
                    create_wo17_position_machine(snapshot),
                    _attestation(
                        snapshot, entry_at=entry_at, attested_at=attested_at
                    ),
                )
            assert found.value.failure is Wo17PositionFailure.ENTRY_CUTOFF_REACHED


def test_market_observation_cannot_activate_live(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path, choice=Wo16SponsorDecision.LIVE)
    with pytest.raises(Wo17PositionRejected) as found:
        apply_paper_observation(
            create_wo17_position_machine(snapshot), _observation(snapshot, "100", 1)
        )
    assert found.value.failure is Wo17PositionFailure.POSITION_MODE_MISMATCH


def test_pre_entry_invalidation_is_terminal_and_preserves_exact_wo13_facts(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path)
    machine = create_wo17_position_machine(snapshot)
    fact = create_wo17_pre_entry_invalidation_fact(
        snapshot=snapshot,
        observed_at=snapshot.bound_at + timedelta(seconds=1),
        source_evidence_identity="GOVERNED-INVALIDATION-FACT-1",
        provenance=("WO-13-EXACT-FACTS",),
    )
    assert (fact.entry_reference, fact.stop, fact.thesis_invalidation_reference) == (
        snapshot.lineage.entry_reference,
        snapshot.lineage.stop,
        snapshot.lineage.thesis_invalidation_reference,
    )
    terminal = apply_pre_entry_invalidation(machine, fact)
    assert terminal.current.state is Wo17PositionState.ENTRY_INVALIDATED_BEFORE_POSITION
    assert terminal.current.position_evidence is None
    with pytest.raises(Wo17PositionRejected) as found:
        apply_paper_observation(terminal.current, _observation(snapshot, "100", 1))
    assert found.value.failure is Wo17PositionFailure.POSITION_STATE_TERMINAL


def test_entry_window_expiry_is_terminal_without_forced_position_or_close(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path)
    machine = create_wo17_position_machine(snapshot)
    before = datetime.combine(snapshot.lineage.trading_date, datetime.min.time(), tzinfo=IST).replace(
        hour=14, minute=59, second=59
    )
    with pytest.raises(Wo17PositionRejected) as found:
        expire_entry_window(machine, expired_at=before)
    assert found.value.failure is Wo17PositionFailure.ENTRY_WINDOW_NOT_EXPIRED
    terminal = expire_entry_window(machine, expired_at=before + timedelta(seconds=1))
    assert terminal.current.state is Wo17PositionState.ENTRY_WINDOW_EXPIRED
    assert terminal.current.position_evidence is None
    assert terminal.current.closure_authority is False


def test_duplicate_older_equal_time_and_conflicting_bytes_fail_closed(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path)
    machine = create_wo17_position_machine(snapshot)
    first_observation = _observation(snapshot, "99", 10)
    first = apply_paper_observation(machine, first_observation)
    replay = apply_paper_observation(first.current, first_observation)
    assert replay.replayed and replay.current is first.current

    with pytest.raises(Wo17PositionRejected) as bytes_conflict:
        apply_paper_observation(
            first.current,
            _observation(snapshot, "98", 11, sequence_identity=first_observation.source_sequence_identity),
        )
    assert bytes_conflict.value.failure is Wo17PositionFailure.SOURCE_SEQUENCE_CONFLICT

    with pytest.raises(Wo17PositionRejected) as duplicate_number:
        apply_paper_observation(first.current, _observation(snapshot, "98", 10))
    assert duplicate_number.value.failure is Wo17PositionFailure.SOURCE_SEQUENCE_CONFLICT

    with pytest.raises(Wo17PositionRejected) as equal_time:
        apply_paper_observation(
            first.current,
            _observation(snapshot, "98", 11, observed_at=first_observation.observed_at),
        )
    assert equal_time.value.failure is Wo17PositionFailure.OBSERVATION_EQUAL_TIME_CONFLICT

    with pytest.raises(Wo17PositionRejected) as older:
        apply_paper_observation(
            first.current,
            _observation(snapshot, "98", 9, observed_at=first_observation.observed_at - timedelta(seconds=1)),
        )
    assert older.value.failure is Wo17PositionFailure.OBSERVATION_OLDER_THAN_CURRENT


def test_sequence_gap_cannot_manufacture_crossing(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path)
    entry = snapshot.lineage.entry_reference
    first = apply_paper_observation(
        create_wo17_position_machine(snapshot), _observation(snapshot, str(entry - 1), 1)
    )
    gap = apply_paper_observation(
        first.current, _observation(snapshot, str(entry + 1), 3)
    )
    assert gap.event is Wo17PositionEvent.ENTRY_SEQUENCE_UNRESOLVED
    assert gap.current.state is Wo17PositionState.PAPER_ARMED
    assert gap.current.position_evidence is None
    beyond = apply_paper_observation(
        gap.current, _observation(snapshot, str(entry + 2), 4)
    )
    assert beyond.current.position_evidence is None


def test_interruption_and_recovery_require_fresh_baseline(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path)
    entry = snapshot.lineage.entry_reference
    first = apply_paper_observation(
        create_wo17_position_machine(snapshot), _observation(snapshot, str(entry - 1), 1)
    )
    interrupted = interrupt_paper_entry_sequence(
        first.current, occurred_at=first.current.last_transition_at + timedelta(seconds=1)
    )
    assert interrupted.current.baseline is None
    with pytest.raises(Wo17PositionRejected) as unavailable:
        apply_paper_observation(
            interrupted.current,
            _observation(
                snapshot,
                str(entry + 1),
                2,
                observed_at=interrupted.current.last_transition_at + timedelta(seconds=1),
            ),
        )
    assert unavailable.value.failure is Wo17PositionFailure.CONTINUITY_TRANSITION_INVALID
    recovered = recover_paper_entry_sequence(
        interrupted.current,
        recovered_at=interrupted.current.last_transition_at + timedelta(seconds=1),
    )
    assert recovered.current.continuity is Wo17EntryContinuity.RECOVERING
    fresh = apply_paper_observation(
        recovered.current,
        _observation(
            snapshot,
            str(entry + 1),
            2,
            observed_at=recovered.current.last_transition_at + timedelta(seconds=1),
        ),
    )
    assert fresh.event is Wo17PositionEvent.PAPER_BASELINE_OBSERVED
    assert fresh.current.position_evidence is None


def test_foreign_lineage_and_existing_position_activation_fail_closed(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path / "first")
    _, foreign = _snapshot(tmp_path / "foreign", direction=SemanticDirection.SHORT)
    machine = create_wo17_position_machine(snapshot)
    with pytest.raises(Wo17PositionRejected) as mismatch:
        apply_paper_observation(machine, _observation(foreign, "99", 1))
    assert mismatch.value.failure is Wo17PositionFailure.UPSTREAM_LINEAGE_MISMATCH

    blocked = create_wo17_position_machine(
        snapshot,
        blocking_non_closed_position_identity="INTRADAY-WO17-PRIOR-SESSION-POSITION",
    )
    entry = snapshot.lineage.entry_reference
    first = apply_paper_observation(blocked, _observation(snapshot, str(entry - 1), 1))
    with pytest.raises(Wo17PositionRejected) as cardinality:
        apply_paper_observation(first.current, _observation(snapshot, str(entry), 2))
    assert cardinality.value.failure is Wo17PositionFailure.EXISTING_NON_CLOSED_POSITION
    assert blocked.blocking_non_closed_position_identity is not None


def test_nse_and_mcx_position_evidence_preserve_exact_instrument_lineage(tmp_path) -> None:
    for mcx in (False, True):
        _, snapshot = _snapshot(tmp_path / str(mcx), mcx=mcx)
        entry = snapshot.lineage.entry_reference
        result = _cross(
            create_wo17_position_machine(snapshot),
            first=str(entry - Decimal("0.05")),
            second=str(entry),
        )
        evidence = result.current.position_evidence
        assert evidence is not None
        assert evidence.instrument_identity == snapshot.lineage.instrument_identity
        assert evidence.actual_contract_identity == snapshot.lineage.actual_contract_identity
        assert evidence.roll_lineage_identity == snapshot.lineage.roll_lineage_identity
        assert (evidence.actual_contract_identity is not None) is (
            snapshot.lineage.market_family is IntradayMarketFamily.MCX
        )


def test_live_exact_replay_is_idempotent_and_state_is_immutable(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path, choice=Wo16SponsorDecision.LIVE)
    machine = create_wo17_position_machine(snapshot)
    attestation = _attestation(snapshot)
    active = apply_live_entry_attestation(machine, attestation)
    replay = apply_live_entry_attestation(active.current, attestation)
    assert replay.replayed and replay.current is active.current
    with pytest.raises(FrozenInstanceError):
        active.current.state = Wo17PositionState.PAPER_ACTIVE


def test_position_evidence_has_no_fill_quantity_economics_or_operational_authority(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path)
    entry = snapshot.lineage.entry_reference
    active = _cross(
        create_wo17_position_machine(snapshot),
        first=str(entry - Decimal("0.05")),
        second=str(entry),
    ).current
    evidence = active.position_evidence
    assert evidence is not None
    assert {evidence.fill, evidence.quantity, evidence.fees, evidence.monetary_pnl, evidence.realised_r} == {
        "UNAVAILABLE"
    }
    assert not any(
        value
        for name, value in asdict(evidence).items()
        if name.endswith("_authority") or name == "broker_acknowledgement"
    )
    assert not any(
        value
        for name, value in asdict(active).items()
        if name.endswith("_authority")
    )
