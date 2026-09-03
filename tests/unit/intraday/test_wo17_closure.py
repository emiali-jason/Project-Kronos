from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo16 import Wo16SponsorDecision
from kronos.intraday.wo17 import Wo17ContractError
from kronos.intraday.wo17_closure import (
    Wo17ClosureFailure,
    Wo17ClosureReason,
    Wo17ClosureRejected,
    Wo17ClosureState,
    Wo17ClosureTransitionCode,
    Wo17NotificationWorthyEvent,
    close_wo17_live_position,
    close_wo17_paper_position,
    create_wo17_closure_machine,
    create_wo17_live_exit_attestation,
    record_wo17_assessment_events,
    record_wo17_monitoring_event,
    record_wo17_position_entry_event,
    record_wo17_session_end_event,
    reject_wo17_manual_paper_closure,
)
from kronos.intraday.wo17_lifecycle import (
    Wo17LifecycleEvent,
    Wo17MonitoringAvailability,
    create_wo17_session_end_fact,
    end_wo17_lifecycle_session,
    interrupt_wo17_lifecycle,
    observe_wo17_lifecycle,
    recover_wo17_lifecycle,
)
from kronos.intraday.wo17_position import Wo17PositionState

from .test_wo17_lifecycle import _active, _baseline, _life_observation, _lifecycle


def _assessed(  # type: ignore[no-untyped-def]
    tmp_path,
    *,
    choice=Wo16SponsorDecision.PAPER,
    direction=SemanticDirection.LONG,
    event="stop",
    mcx=False,
):
    _, position, lifecycle = _lifecycle(
        tmp_path, choice=choice, direction=direction, mcx=mcx
    )
    baseline = _baseline(
        lifecycle,
        sequence=1 if choice is Wo16SponsorDecision.LIVE else None,
    )
    lineage = position.upstream_snapshot.lineage
    sequence = baseline.current.baseline.source_sequence + 1  # type: ignore[union-attr]
    price = getattr(lineage, "canonical_target" if event == "target" else event)
    result = observe_wo17_lifecycle(
        baseline.current,
        _life_observation(baseline.current, str(price), sequence),
    )
    assert result.assessment is not None
    return position, result.current, result.assessment


@pytest.mark.parametrize(
    ("direction", "event", "reason"),
    (
        (SemanticDirection.LONG, "stop", Wo17ClosureReason.STOP_OBSERVED),
        (SemanticDirection.LONG, "target", Wo17ClosureReason.TARGET_OBSERVED),
        (SemanticDirection.SHORT, "stop", Wo17ClosureReason.STOP_OBSERVED),
        (SemanticDirection.SHORT, "target", Wo17ClosureReason.TARGET_OBSERVED),
    ),
)
def test_ordered_paper_stop_and_target_close_long_and_short(
    tmp_path, direction, event, reason
) -> None:
    position, lifecycle, assessment = _assessed(
        tmp_path, direction=direction, event=event
    )
    machine = create_wo17_closure_machine(position)
    result = close_wo17_paper_position(machine, lifecycle, assessment)

    assert result.transition_code is Wo17ClosureTransitionCode.PAPER_CLOSED
    assert result.current.closure_state is Wo17ClosureState.PAPER_CLOSED
    assert result.current.position is position
    assert result.closure is not None
    assert result.closure.closure_reason is reason
    assert result.closure.source_identity == assessment.assessment_identity
    assert result.closure.exit_timestamp == assessment.assessed_at
    assert result.events[0].event_type is Wo17NotificationWorthyEvent.PAPER_CLOSED
    assert result.events[0].notification_delivered is False


def test_ambiguous_stop_target_ordering_creates_no_closure(tmp_path) -> None:
    _, position, lifecycle = _lifecycle(tmp_path)
    baseline = _baseline(lifecycle)
    lineage = position.upstream_snapshot.lineage
    sequence = baseline.current.baseline.source_sequence + 1  # type: ignore[union-attr]
    ambiguous = observe_wo17_lifecycle(
        baseline.current,
        _life_observation(
            baseline.current,
            str(lineage.entry_reference),
            sequence,
            low=str(min(lineage.stop, lineage.canonical_target)),
            high=str(max(lineage.stop, lineage.canonical_target)),
        ),
    )
    assert ambiguous.assessment is not None
    machine = create_wo17_closure_machine(position)
    with pytest.raises(Wo17ClosureRejected) as found:
        close_wo17_paper_position(
            machine, ambiguous.current, ambiguous.assessment
        )
    assert found.value.failure is (
        Wo17ClosureFailure.LIFECYCLE_EVENT_ORDER_UNRESOLVED
    )
    assert machine.closure is None
    assert machine.closure_state is Wo17ClosureState.ACTIVE


def test_invalidation_and_session_end_never_close_paper(tmp_path) -> None:
    position, lifecycle, invalidation = _assessed(tmp_path, event="thesis_invalidation_reference")
    assert invalidation.invalidation_observed
    machine = create_wo17_closure_machine(position)
    observed = record_wo17_assessment_events(machine, lifecycle, invalidation)
    assert Wo17NotificationWorthyEvent.INVALIDATION_OBSERVED in {
        item.event_type for item in observed.events
    }
    assert observed.current.closure is None
    assert observed.current.closure_state is Wo17ClosureState.ACTIVE

    lineage = position.upstream_snapshot.lineage
    fact = create_wo17_session_end_fact(
        machine=lifecycle,
        observed_at=lineage.active_window_closes_at,
        source_fact_identity="DOMAIN-008-SESSION-END",
        provenance=("DOMAIN-008", "ADR-0027"),
    )
    ended = end_wo17_lifecycle_session(lifecycle, fact)
    event_result = record_wo17_session_end_event(
        observed.current, ended.current, fact
    )
    assert event_result.current.closure is None
    assert event_result.current.closure_state is Wo17ClosureState.ACTIVE
    assert event_result.events[0].event_type is Wo17NotificationWorthyEvent.SESSION_ENDED


def test_manual_paper_closure_is_prohibited(tmp_path) -> None:
    _, position = _active(tmp_path)
    machine = create_wo17_closure_machine(position)
    with pytest.raises(Wo17ClosureRejected) as found:
        reject_wo17_manual_paper_closure(machine)
    assert found.value.failure is Wo17ClosureFailure.MANUAL_PAPER_CLOSURE_PROHIBITED
    assert machine.closure is None


def test_exact_live_exit_attestation_closes_without_broker_claim(tmp_path) -> None:
    _, position = _active(tmp_path, choice=Wo16SponsorDecision.LIVE)
    machine = create_wo17_closure_machine(position)
    evidence = position.position_evidence
    assert evidence is not None
    exit_at = evidence.entry_timestamp + timedelta(hours=7)
    attestation = create_wo17_live_exit_attestation(
        machine=machine,
        actual_exit_price=Decimal("101.25"),
        actual_exit_timestamp=exit_at,
        attestation_operation_timestamp=exit_at + timedelta(minutes=1),
        sponsor_operation_identity="SPONSOR-WO17-LIVE-EXIT-1",
        bounded_manual_action_provenance=("SAME-ORIGIN-SPONSOR-ACTION",),
    )
    result = close_wo17_live_position(machine, attestation)

    assert result.transition_code is Wo17ClosureTransitionCode.LIVE_CLOSED
    assert result.current.closure_state is Wo17ClosureState.LIVE_CLOSED
    assert result.current.position is position
    assert result.closure is not None
    assert result.closure.exit_price == Decimal("101.25")
    assert result.closure.live_exit_attestation_identity == (
        attestation.attestation_identity
    )
    assert result.closure.broker_confirmation is False
    assert result.closure.broker_fill == "UNAVAILABLE"
    assert result.events[0].event_type is (
        Wo17NotificationWorthyEvent.LIVE_CLOSURE_ATTESTED
    )


@pytest.mark.parametrize("event", ("stop", "target", "thesis_invalidation_reference"))
def test_live_lifecycle_observations_do_not_close(event, tmp_path) -> None:
    position, lifecycle, assessment = _assessed(
        tmp_path, choice=Wo16SponsorDecision.LIVE, event=event
    )
    machine = create_wo17_closure_machine(position)
    recorded = record_wo17_assessment_events(machine, lifecycle, assessment)
    assert recorded.current.position is position
    assert recorded.current.closure is None
    assert recorded.current.closure_state is Wo17ClosureState.ACTIVE
    with pytest.raises(Wo17ClosureRejected) as found:
        close_wo17_paper_position(machine, lifecycle, assessment)
    assert found.value.failure is Wo17ClosureFailure.POSITION_MODE_MISMATCH


def test_live_session_end_does_not_close(tmp_path) -> None:
    _, position, lifecycle = _lifecycle(
        tmp_path, choice=Wo16SponsorDecision.LIVE
    )
    lineage = position.upstream_snapshot.lineage
    fact = create_wo17_session_end_fact(
        machine=lifecycle,
        observed_at=lineage.active_window_closes_at,
        source_fact_identity="DOMAIN-008-LIVE-SESSION-END",
        provenance=("DOMAIN-008", "ADR-0027"),
    )
    ended = end_wo17_lifecycle_session(lifecycle, fact)
    result = record_wo17_session_end_event(
        create_wo17_closure_machine(position), ended.current, fact
    )
    assert result.current.closure_state is Wo17ClosureState.ACTIVE
    assert result.current.closure is None


def test_live_exit_does_not_reuse_entry_cutoff_as_exit_cutoff(tmp_path) -> None:
    _, position = _active(tmp_path, choice=Wo16SponsorDecision.LIVE)
    machine = create_wo17_closure_machine(position)
    evidence = position.position_evidence
    assert evidence is not None
    exit_at = position.upstream_snapshot.lineage.active_window_closes_at + timedelta(hours=1)
    attestation = create_wo17_live_exit_attestation(
        machine=machine,
        actual_exit_price=Decimal("99.5"),
        actual_exit_timestamp=exit_at,
        attestation_operation_timestamp=exit_at + timedelta(seconds=1),
        sponsor_operation_identity="SPONSOR-AFTER-ENTRY-CUTOFF",
        bounded_manual_action_provenance=("SPONSOR-ATTESTED-ACTUAL-EXIT",),
    )
    assert close_wo17_live_position(machine, attestation).closure is not None


def test_naive_invalid_and_temporally_invalid_live_exit_is_rejected(tmp_path) -> None:
    _, position = _active(tmp_path, choice=Wo16SponsorDecision.LIVE)
    machine = create_wo17_closure_machine(position)
    evidence = position.position_evidence
    assert evidence is not None
    valid_at = evidence.entry_timestamp + timedelta(minutes=1)

    for price, exit_at, attested_at, failure in (
        (
            Decimal("NaN"),
            valid_at,
            valid_at + timedelta(seconds=1),
            Wo17ClosureFailure.SOURCE_CONTRACT_INVALID,
        ),
        (
            Decimal("100"),
            valid_at.replace(tzinfo=None),
            valid_at + timedelta(seconds=1),
            Wo17ClosureFailure.SOURCE_CONTRACT_INVALID,
        ),
        (
            Decimal("100"),
            evidence.entry_timestamp - timedelta(seconds=1),
            valid_at,
            Wo17ClosureFailure.LIVE_EXIT_BEFORE_ENTRY,
        ),
        (
            Decimal("100"),
            valid_at,
            valid_at - timedelta(seconds=1),
            Wo17ClosureFailure.LIVE_ATTESTATION_BEFORE_EXIT,
        ),
    ):
        with pytest.raises(Wo17ClosureRejected) as found:
            create_wo17_live_exit_attestation(
                machine=machine,
                actual_exit_price=price,
                actual_exit_timestamp=exit_at,
                attestation_operation_timestamp=attested_at,
                sponsor_operation_identity="SPONSOR-INVALID-EXIT",
                bounded_manual_action_provenance=("SPONSOR-ACTION",),
            )
        assert found.value.failure is failure


def test_exact_closure_replay_is_idempotent_and_conflict_fails_closed(tmp_path) -> None:
    _, position = _active(tmp_path, choice=Wo16SponsorDecision.LIVE)
    machine = create_wo17_closure_machine(position)
    evidence = position.position_evidence
    assert evidence is not None
    exit_at = evidence.entry_timestamp + timedelta(minutes=5)

    def attestation(price, identity):  # type: ignore[no-untyped-def]
        return create_wo17_live_exit_attestation(
            machine=machine,
            actual_exit_price=Decimal(price),
            actual_exit_timestamp=exit_at,
            attestation_operation_timestamp=exit_at + timedelta(seconds=1),
            sponsor_operation_identity=identity,
            bounded_manual_action_provenance=("SPONSOR-ACTION",),
        )

    first_attestation = attestation("101", "SPONSOR-EXIT-ONE")
    first = close_wo17_live_position(machine, first_attestation)
    replay = close_wo17_live_position(first.current, first_attestation)
    assert replay.replayed and not replay.applied
    assert replay.current is first.current
    assert replay.closure is first.closure
    assert len(replay.current.events) == 1

    with pytest.raises(Wo17ClosureRejected) as conflict:
        close_wo17_live_position(
            first.current, attestation("102", "SPONSOR-EXIT-TWO")
        )
    assert conflict.value.failure is Wo17ClosureFailure.CLOSURE_CONFLICT
    assert first.current.closure is first.closure


def test_stale_and_foreign_lifecycle_lineage_fail_closed(tmp_path) -> None:
    position, stopped_lifecycle, stopped = _assessed(tmp_path / "current")
    newer = observe_wo17_lifecycle(
        stopped_lifecycle,
        _life_observation(
            stopped_lifecycle,
            str(position.upstream_snapshot.lineage.entry_reference),
            stopped_lifecycle.baseline.source_sequence + 1,  # type: ignore[union-attr]
        ),
    )
    machine = create_wo17_closure_machine(position)
    with pytest.raises(Wo17ClosureRejected) as stale:
        close_wo17_paper_position(machine, newer.current, stopped)
    assert stale.value.failure is Wo17ClosureFailure.STALE_LIFECYCLE_EVIDENCE

    _, foreign_lifecycle, foreign = _assessed(
        tmp_path / "foreign", direction=SemanticDirection.SHORT
    )
    with pytest.raises(Wo17ClosureRejected) as mismatch:
        close_wo17_paper_position(machine, foreign_lifecycle, foreign)
    assert mismatch.value.failure is Wo17ClosureFailure.POSITION_BINDING_MISMATCH


def test_entry_monitoring_and_assessment_events_are_notification_worthy_only(
    tmp_path,
) -> None:
    _, position, lifecycle = _lifecycle(tmp_path)
    machine = create_wo17_closure_machine(position)
    entry = record_wo17_position_entry_event(machine)
    assert entry.events[0].event_type is (
        Wo17NotificationWorthyEvent.PAPER_ENTRY_OBSERVED
    )

    baseline = _baseline(lifecycle)
    interrupted = interrupt_wo17_lifecycle(
        baseline.current,
        occurred_at=baseline.current.last_transition_at + timedelta(seconds=1),
    )
    interruption = record_wo17_monitoring_event(entry.current, interrupted)
    recovered = recover_wo17_lifecycle(
        interrupted.current,
        recovered_at=interrupted.current.last_transition_at + timedelta(seconds=1),
    )
    recovery = record_wo17_monitoring_event(interruption.current, recovered)
    assert tuple(item.event_type for item in recovery.current.events) == (
        Wo17NotificationWorthyEvent.PAPER_ENTRY_OBSERVED,
        Wo17NotificationWorthyEvent.MONITORING_INTERRUPTED,
        Wo17NotificationWorthyEvent.MONITORING_RECOVERED,
    )
    assert all(item.notification_worthy for item in recovery.current.events)
    assert not any(item.notification_delivered for item in recovery.current.events)
    assert not any(
        item.notification_delivery_authority for item in recovery.current.events
    )


def test_event_replay_and_conflicting_bytes_are_rejected(tmp_path) -> None:
    _, position = _active(tmp_path)
    machine = create_wo17_closure_machine(position)
    first = record_wo17_position_entry_event(machine)
    replay = record_wo17_position_entry_event(first.current)
    assert replay.replayed and replay.current is first.current

    with pytest.raises(Wo17ContractError):
        replace(first.events[0], provenance=("DIFFERENT-BYTES",))


@pytest.mark.parametrize("mcx", (False, True))
def test_event_and_closure_preserve_exact_nse_mcx_lineage(tmp_path, mcx) -> None:
    position, lifecycle, assessment = _assessed(tmp_path, mcx=mcx)
    result = close_wo17_paper_position(
        create_wo17_closure_machine(position), lifecycle, assessment
    )
    closure = result.closure
    assert closure is not None
    lineage = position.upstream_snapshot.lineage
    assert closure.upstream_lineage_identity == lineage.lineage_identity
    assert closure.actual_contract_identity == lineage.actual_contract_identity
    assert closure.roll_lineage_identity == lineage.roll_lineage_identity
    assert result.events[0].actual_contract_identity == lineage.actual_contract_identity
    assert result.current.position is position


def test_contracts_are_immutable_and_have_no_delivery_or_economic_authority(
    tmp_path,
) -> None:
    position, lifecycle, assessment = _assessed(tmp_path)
    result = close_wo17_paper_position(
        create_wo17_closure_machine(position), lifecycle, assessment
    )
    assert result.closure is not None
    with pytest.raises(FrozenInstanceError):
        result.closure.exit_price = Decimal("0")

    assert {
        result.closure.broker_fill,
        result.closure.quantity,
        result.closure.fees,
        result.closure.monetary_pnl,
        result.closure.realised_r,
        result.current.quantity,
        result.current.fees,
        result.current.monetary_pnl,
        result.current.realised_r,
    } == {"UNAVAILABLE"}
    assert not any(
        value
        for name, value in asdict(result.current).items()
        if name.endswith("_authority")
    )
    assert not any(
        value
        for name, value in asdict(result.closure).items()
        if name.endswith("_authority")
    )
    assert result.current.position.state is Wo17PositionState.PAPER_ACTIVE
    assert result.current.closure_state is Wo17ClosureState.PAPER_CLOSED
