from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo16 import Wo16SponsorDecision
from kronos.intraday.wo17_lifecycle import (
    Wo17LifecycleAssessmentCode,
    Wo17LifecycleEvent,
    Wo17LifecycleFailure,
    Wo17LifecycleRejected,
    Wo17MonitoringAvailability,
    create_wo17_lifecycle_machine,
    create_wo17_lifecycle_observation,
    create_wo17_session_end_fact,
    end_wo17_lifecycle_session,
    interrupt_wo17_lifecycle,
    observe_wo17_lifecycle,
    recover_wo17_lifecycle,
)
from kronos.intraday.wo17_position import (
    Wo17PositionState,
    apply_live_entry_attestation,
    apply_paper_observation,
    apply_pre_entry_invalidation,
    create_wo17_live_entry_attestation,
    create_wo17_position_machine,
    create_wo17_pre_entry_invalidation_fact,
)

from .test_wo17_position import _attestation, _observation, _snapshot


def _active(  # type: ignore[no-untyped-def]
    tmp_path,
    *,
    choice=Wo16SponsorDecision.PAPER,
    direction=SemanticDirection.LONG,
    mcx=False,
):
    _, snapshot = _snapshot(
        tmp_path, choice=choice, direction=direction, mcx=mcx
    )
    position = create_wo17_position_machine(snapshot)
    if choice is Wo16SponsorDecision.LIVE:
        position = apply_live_entry_attestation(position, _attestation(snapshot)).current
    else:
        entry = snapshot.lineage.entry_reference
        first = entry - Decimal("0.05") if direction is SemanticDirection.LONG else entry + Decimal("0.05")
        position = apply_paper_observation(
            position, _observation(snapshot, str(first), 1)
        ).current
        position = apply_paper_observation(
            position, _observation(snapshot, str(entry), 2)
        ).current
    assert position.state in {
        Wo17PositionState.PAPER_ACTIVE,
        Wo17PositionState.LIVE_ACTIVE,
    }
    return snapshot, position


def _lifecycle(tmp_path, **kwargs):  # type: ignore[no-untyped-def]
    snapshot, position = _active(tmp_path, **kwargs)
    return snapshot, position, create_wo17_lifecycle_machine(position)


def _life_observation(  # type: ignore[no-untyped-def]
    machine,
    price,
    sequence,
    *,
    observed_at=None,
    sequence_identity=None,
    low=None,
    high=None,
):
    return create_wo17_lifecycle_observation(
        machine=machine,
        provider_identity="DOMAIN-006-READ-ONLY-FACT",
        observed_price=Decimal(price),
        observed_low=None if low is None else Decimal(low),
        observed_high=None if high is None else Decimal(high),
        observed_at=observed_at
        or machine.last_transition_at + timedelta(seconds=sequence),
        source_sequence_identity=sequence_identity
        or f"LIFECYCLE-SEQUENCE-{sequence}",
        source_sequence=sequence,
        provenance=("ADR-0027", "WO-17-SLICE-3-TEST"),
    )


def _baseline(machine, *, sequence=None):  # type: ignore[no-untyped-def]
    if sequence is None:
        evidence = machine.position.position_evidence
        assert evidence is not None
        sequence = (evidence.source_sequence or 0) + 1
    return observe_wo17_lifecycle(
        machine,
        _life_observation(
            machine,
            str(machine.position.upstream_snapshot.lineage.entry_reference),
            sequence,
        ),
    )


@pytest.mark.parametrize(
    ("choice", "expected"),
    (
        (Wo16SponsorDecision.PAPER, Wo17PositionState.PAPER_ACTIVE),
        (Wo16SponsorDecision.LIVE, Wo17PositionState.LIVE_ACTIVE),
    ),
)
def test_only_paper_active_and_live_active_are_admitted(tmp_path, choice, expected) -> None:
    _, position = _active(tmp_path, choice=choice)
    machine = create_wo17_lifecycle_machine(position)
    assert machine.position_state is expected
    assert machine.monitoring_availability is Wo17MonitoringAvailability.AVAILABLE
    assert machine.position is position


def test_inactive_and_terminal_position_states_are_rejected(tmp_path) -> None:
    _, snapshot = _snapshot(tmp_path / "inactive")
    inactive = create_wo17_position_machine(snapshot)
    with pytest.raises(Wo17LifecycleRejected) as found:
        create_wo17_lifecycle_machine(inactive)
    assert found.value.failure is Wo17LifecycleFailure.POSITION_NOT_ACTIVE

    fact = create_wo17_pre_entry_invalidation_fact(
        snapshot=snapshot,
        observed_at=snapshot.bound_at + timedelta(seconds=1),
        source_evidence_identity="GOVERNED-PRE-ENTRY-INVALIDATION",
        provenance=("WO-13-EXACT-FACTS",),
    )
    terminal = apply_pre_entry_invalidation(inactive, fact).current
    with pytest.raises(Wo17LifecycleRejected) as terminal_found:
        create_wo17_lifecycle_machine(terminal)
    assert terminal_found.value.failure is Wo17LifecycleFailure.POSITION_NOT_ACTIVE


@pytest.mark.parametrize(
    "direction", (SemanticDirection.LONG, SemanticDirection.SHORT)
)
def test_long_and_short_stop_target_assessment_is_inclusive(tmp_path, direction) -> None:
    _, _, machine = _lifecycle(tmp_path, direction=direction)
    baseline = _baseline(machine)
    lineage = machine.position.upstream_snapshot.lineage
    sequence = baseline.current.baseline.source_sequence + 1  # type: ignore[union-attr]

    stopped = observe_wo17_lifecycle(
        baseline.current,
        _life_observation(baseline.current, str(lineage.stop), sequence),
    )
    assert stopped.assessment is not None
    assert stopped.assessment.stop_observed is True
    assert Wo17LifecycleEvent.STOP_OBSERVED in stopped.assessment.observed_events
    assert stopped.current.position_state is machine.position_state
    assert stopped.assessment.position_closed is False

    _, _, fresh = _lifecycle(tmp_path / "target", direction=direction)
    target_baseline = _baseline(fresh)
    target_sequence = target_baseline.current.baseline.source_sequence + 1  # type: ignore[union-attr]
    targeted = observe_wo17_lifecycle(
        target_baseline.current,
        _life_observation(
            target_baseline.current,
            str(fresh.position.upstream_snapshot.lineage.canonical_target),
            target_sequence,
        ),
    )
    assert targeted.assessment is not None
    assert targeted.assessment.target_observed is True
    assert Wo17LifecycleEvent.TARGET_OBSERVED in targeted.assessment.observed_events
    assert targeted.assessment.position_closed is False


def test_post_entry_invalidation_is_factual_and_never_closes(tmp_path) -> None:
    _, _, machine = _lifecycle(tmp_path)
    baseline = _baseline(machine)
    lineage = machine.position.upstream_snapshot.lineage
    sequence = baseline.current.baseline.source_sequence + 1  # type: ignore[union-attr]
    result = observe_wo17_lifecycle(
        baseline.current,
        _life_observation(
            baseline.current,
            str(lineage.thesis_invalidation_reference),
            sequence,
        ),
    )
    assert result.assessment is not None
    assert result.assessment.invalidation_observed is True
    assert Wo17LifecycleEvent.INVALIDATION_OBSERVED in result.assessment.observed_events
    assert result.assessment.position_closed is False
    assert result.current.position_state is Wo17PositionState.PAPER_ACTIVE


@pytest.mark.parametrize("level", ("stop", "canonical_target"))
def test_live_stop_and_target_are_observations_without_closure(tmp_path, level) -> None:
    _, _, machine = _lifecycle(tmp_path, choice=Wo16SponsorDecision.LIVE)
    baseline = _baseline(machine, sequence=1)
    lineage = machine.position.upstream_snapshot.lineage
    result = observe_wo17_lifecycle(
        baseline.current,
        _life_observation(baseline.current, str(getattr(lineage, level)), 2),
    )
    assert result.assessment is not None
    assert result.assessment.observed_events
    assert result.assessment.position_closed is False
    assert result.current.position_state is Wo17PositionState.LIVE_ACTIVE
    assert result.current.position is machine.position


def test_same_observation_stop_target_range_is_order_unresolved(tmp_path) -> None:
    _, _, machine = _lifecycle(tmp_path)
    baseline = _baseline(machine)
    lineage = machine.position.upstream_snapshot.lineage
    sequence = baseline.current.baseline.source_sequence + 1  # type: ignore[union-attr]
    result = observe_wo17_lifecycle(
        baseline.current,
        _life_observation(
            baseline.current,
            str(lineage.entry_reference),
            sequence,
            low=str(min(lineage.stop, lineage.canonical_target)),
            high=str(max(lineage.stop, lineage.canonical_target)),
        ),
    )
    assert result.assessment is not None
    assert result.assessment.ordering_unresolved is True
    assert result.assessment.observed_events == (
        Wo17LifecycleEvent.LIFECYCLE_EVENT_ORDER_UNRESOLVED,
    )
    assert result.assessment.stop_observed is result.assessment.target_observed is True
    assert result.assessment.position_closed is False


def test_exact_replay_and_all_ordering_conflicts_fail_closed(tmp_path) -> None:
    _, _, machine = _lifecycle(tmp_path)
    observation = _life_observation(machine, "100", 3)
    first = observe_wo17_lifecycle(machine, observation)
    replay = observe_wo17_lifecycle(first.current, observation)
    assert replay.replayed and replay.current is first.current

    with pytest.raises(Wo17LifecycleRejected) as bytes_conflict:
        observe_wo17_lifecycle(
            first.current,
            _life_observation(
                first.current,
                "101",
                4,
                sequence_identity=observation.source_sequence_identity,
            ),
        )
    assert bytes_conflict.value.failure is Wo17LifecycleFailure.SOURCE_SEQUENCE_CONFLICT

    with pytest.raises(Wo17LifecycleRejected) as duplicate_sequence:
        observe_wo17_lifecycle(
            first.current, _life_observation(first.current, "101", 3)
        )
    assert duplicate_sequence.value.failure is Wo17LifecycleFailure.SOURCE_SEQUENCE_CONFLICT

    with pytest.raises(Wo17LifecycleRejected) as equal_time:
        observe_wo17_lifecycle(
            first.current,
            _life_observation(
                first.current,
                "101",
                4,
                observed_at=observation.observed_at,
            ),
        )
    assert equal_time.value.failure is Wo17LifecycleFailure.OBSERVATION_EQUAL_TIME_CONFLICT

    with pytest.raises(Wo17LifecycleRejected) as older:
        observe_wo17_lifecycle(
            first.current,
            _life_observation(
                first.current,
                "101",
                0,
                observed_at=observation.observed_at - timedelta(seconds=1),
            ),
        )
    assert older.value.failure is Wo17LifecycleFailure.OBSERVATION_OLDER_THAN_CURRENT


def test_sequence_gap_resets_baseline_without_inferred_event(tmp_path) -> None:
    _, _, machine = _lifecycle(tmp_path)
    baseline = _baseline(machine)
    lineage = machine.position.upstream_snapshot.lineage
    gap = observe_wo17_lifecycle(
        baseline.current,
        _life_observation(
            baseline.current,
            str(lineage.canonical_target),
            baseline.current.baseline.source_sequence + 2,  # type: ignore[union-attr]
        ),
    )
    assert gap.assessment is not None
    assert gap.assessment.assessment_code is (
        Wo17LifecycleAssessmentCode.SEQUENCE_GAP_BASELINE_ONLY
    )
    assert gap.assessment.observed_events == ()
    assert gap.assessment.target_observed is False
    assert gap.current.position_state is Wo17PositionState.PAPER_ACTIVE


def test_interruption_recovery_requires_event_and_fresh_baseline(tmp_path) -> None:
    _, _, machine = _lifecycle(tmp_path)
    baseline = _baseline(machine)
    interrupted = interrupt_wo17_lifecycle(
        baseline.current,
        occurred_at=baseline.current.last_transition_at + timedelta(seconds=1),
    )
    assert interrupted.current.monitoring_availability is (
        Wo17MonitoringAvailability.INTERRUPTED
    )
    assert interrupted.current.baseline is None
    assert interrupted.current.position is machine.position

    with pytest.raises(Wo17LifecycleRejected) as unavailable:
        observe_wo17_lifecycle(
            interrupted.current,
            _life_observation(
                interrupted.current,
                str(machine.position.upstream_snapshot.lineage.canonical_target),
                4,
                observed_at=interrupted.current.last_transition_at
                + timedelta(seconds=1),
            ),
        )
    assert unavailable.value.failure is Wo17LifecycleFailure.MONITORING_NOT_AVAILABLE

    recovered = recover_wo17_lifecycle(
        interrupted.current,
        recovered_at=interrupted.current.last_transition_at + timedelta(seconds=1),
    )
    fresh = observe_wo17_lifecycle(
        recovered.current,
        _life_observation(
            recovered.current,
            str(machine.position.upstream_snapshot.lineage.canonical_target),
            4,
            observed_at=recovered.current.last_transition_at + timedelta(seconds=1),
        ),
    )
    assert fresh.assessment is not None
    assert fresh.assessment.assessment_code is Wo17LifecycleAssessmentCode.BASELINE_ONLY
    assert fresh.assessment.observed_events == ()
    assert fresh.current.monitoring_availability is Wo17MonitoringAvailability.AVAILABLE
    assert fresh.current.position is machine.position


@pytest.mark.parametrize("mcx", (False, True))
def test_session_end_preserves_position_and_exact_nse_mcx_lineage(tmp_path, mcx) -> None:
    _, position, machine = _lifecycle(tmp_path, mcx=mcx)
    lineage = position.upstream_snapshot.lineage
    fact = create_wo17_session_end_fact(
        machine=machine,
        observed_at=lineage.active_window_closes_at,
        source_fact_identity="DOMAIN-008-GOVERNED-SESSION-END",
        provenance=("DOMAIN-008", "ADR-0027"),
    )
    ended = end_wo17_lifecycle_session(machine, fact)
    assert ended.current.monitoring_availability is Wo17MonitoringAvailability.SESSION_ENDED
    assert ended.current.position is position
    assert ended.current.position_state is position.state
    assert ended.current.position_closure_authority is False
    assert fact.actual_contract_identity == lineage.actual_contract_identity
    assert fact.roll_lineage_identity == lineage.roll_lineage_identity
    assert (fact.actual_contract_identity is not None) is (
        lineage.market_family is IntradayMarketFamily.MCX
    )
    replay = end_wo17_lifecycle_session(ended.current, fact)
    assert replay.replayed and replay.current is ended.current


def test_foreign_position_lineage_is_rejected(tmp_path) -> None:
    _, _, machine = _lifecycle(tmp_path / "one")
    _, _, foreign = _lifecycle(
        tmp_path / "two", direction=SemanticDirection.SHORT
    )
    observation = _life_observation(foreign, "100", 3)
    with pytest.raises(Wo17LifecycleRejected) as found:
        observe_wo17_lifecycle(machine, observation)
    assert found.value.failure is Wo17LifecycleFailure.POSITION_BINDING_MISMATCH


@pytest.mark.parametrize(
    "availability",
    (Wo17MonitoringAvailability.NOT_APPLICABLE, Wo17MonitoringAvailability.UNAVAILABLE),
)
def test_nonavailable_monitoring_states_accept_no_observation(tmp_path, availability) -> None:
    _, position = _active(tmp_path)
    machine = create_wo17_lifecycle_machine(
        position, monitoring_availability=availability
    )
    with pytest.raises(Wo17LifecycleRejected) as found:
        observe_wo17_lifecycle(machine, _life_observation(machine, "100", 3))
    assert found.value.failure is Wo17LifecycleFailure.MONITORING_NOT_AVAILABLE


def test_contracts_are_immutable_and_contain_no_forbidden_authority(tmp_path) -> None:
    _, _, machine = _lifecycle(tmp_path)
    baseline = _baseline(machine)
    assert baseline.assessment is not None
    with pytest.raises(FrozenInstanceError):
        baseline.current.position_state = Wo17PositionState.LIVE_ACTIVE

    assert baseline.current.position is machine.position
    assert not any(
        value
        for name, value in asdict(baseline.current).items()
        if name.endswith("_authority")
    )
    assert not any(
        value
        for name, value in asdict(baseline.assessment).items()
        if name.endswith("_authority") or name in {"position_closed", "position_state_changed"}
    )
    assert {
        baseline.current.quantity,
        baseline.current.fees,
        baseline.current.monetary_pnl,
        baseline.current.realised_r,
    } == {"UNAVAILABLE"}
