from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from kronos.intraday.wo15 import (
    Wo15ContractError,
    Wo15ExpiryCause,
    Wo15QualificationPath,
    Wo15TimingState,
    Wo15TrustFailure,
    bind_cycle_evaluation,
    create_followup_observation,
)
from kronos.intraday.wo15_handoff import (
    WO15_RISK_REFERENCE_SEMANTICS,
    WO15_TIMING_HANDOFF_IDENTITY,
    WO15_TIMING_HANDOFF_VERSION,
    create_wo15_timing_handoff,
)

from .test_wo15_contracts import _evaluation, _evidence, _progression


def _terminal_evaluation(tmp_path, state):  # type: ignore[no-untyped-def]
    if state is not Wo15TimingState.TIMING_EXPIRED:
        return _evaluation(tmp_path, state=state)
    admission, session, _, _, waiting = _evaluation(tmp_path)
    evidence = _evidence(admission, session, minutes_after=10)
    observation, transition = create_followup_observation(
        cycle=waiting.cycle,
        prior_state=Wo15TimingState.TIMING_WAITING,
        current_state=Wo15TimingState.TIMING_EXPIRED,
        evidence=evidence,
        progression=_progression(admission, evidence),
        transition_cause="SESSION_END",
        qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
        observed_at=evidence.candle_end + timedelta(seconds=1),
        expiry_cause=Wo15ExpiryCause.SESSION_END,
    )
    return admission, session, evidence, _progression(admission, evidence), bind_cycle_evaluation(
        cycle=waiting.cycle, observation=observation, transition=transition
    )


@pytest.mark.parametrize(
    "state",
    (
        Wo15TimingState.TIMING_QUALIFIED,
        Wo15TimingState.TIMING_FAILED,
        Wo15TimingState.TIMING_EXPIRED,
        Wo15TimingState.TIMING_UNAVAILABLE,
    ),
)
def test_handoff_supports_exact_governed_states(tmp_path, state) -> None:  # type: ignore[no-untyped-def]
    admission, _, _, _, evaluation = _terminal_evaluation(tmp_path, state)
    handoff = create_wo15_timing_handoff(
        admission=admission,
        evaluation=evaluation,
        handoff_created_at=evaluation.observation.observed_at + timedelta(seconds=1),
    )
    assert handoff.schema_identity == WO15_TIMING_HANDOFF_IDENTITY
    assert handoff.schema_version == WO15_TIMING_HANDOFF_VERSION
    assert handoff.current_state is state


def test_repeated_waiting_has_no_required_downstream_handoff(tmp_path) -> None:
    admission, _, _, _, waiting = _evaluation(tmp_path)
    with pytest.raises(Wo15ContractError, match="WO15_WAITING_HANDOFF_NOT_REQUIRED"):
        create_wo15_timing_handoff(
            admission=admission,
            evaluation=waiting,
            handoff_created_at=waiting.observation.observed_at + timedelta(seconds=1),
        )


def test_handoff_authority_is_timing_evidence_only(tmp_path) -> None:
    admission, _, _, _, qualified = _evaluation(
        tmp_path, state=Wo15TimingState.TIMING_QUALIFIED
    )
    handoff = create_wo15_timing_handoff(
        admission=admission,
        evaluation=qualified,
        handoff_created_at=qualified.observation.observed_at + timedelta(seconds=1),
    )
    assert handoff.timing_evidence_authority is True
    assert {
        handoff.sponsor_decision_authority,
        handoff.paper_authority,
        handoff.live_authority,
        handoff.ignore_authority,
        handoff.position_authority,
        handoff.broker_authority,
    } == {"NONE"}


def test_optional_wo14_reference_is_audit_context_only(tmp_path) -> None:
    admission, _, _, _, qualified = _evaluation(
        tmp_path, state=Wo15TimingState.TIMING_QUALIFIED
    )
    without = create_wo15_timing_handoff(
        admission=admission,
        evaluation=qualified,
        handoff_created_at=qualified.observation.observed_at + timedelta(seconds=1),
    )
    with_context = create_wo15_timing_handoff(
        admission=admission,
        evaluation=qualified,
        handoff_created_at=qualified.observation.observed_at + timedelta(seconds=1),
        wo14_observation_identity="INTRADAY-WO14-OBSERVATION-CONTEXT",
        wo14_observation_integrity="INTEGRITY-INTRADAY-WO14-CONTEXT",
    )
    assert without.wo14_observation_identity is None
    assert with_context.wo14_reference_semantics == WO15_RISK_REFERENCE_SEMANTICS
    assert not hasattr(with_context, "risk_permission")
    assert not hasattr(with_context, "risk_approved")


def test_failed_handoff_references_prior_qualified_without_mutation(tmp_path) -> None:
    admission, session, _, _, qualified = _evaluation(
        tmp_path, state=Wo15TimingState.TIMING_QUALIFIED
    )
    first = create_wo15_timing_handoff(
        admission=admission,
        evaluation=qualified,
        handoff_created_at=qualified.observation.observed_at + timedelta(seconds=1),
    )
    evidence = _evidence(admission, session, minutes_after=10)
    observation, transition = create_followup_observation(
        cycle=qualified.cycle,
        prior_state=Wo15TimingState.TIMING_QUALIFIED,
        current_state=Wo15TimingState.TIMING_FAILED,
        evidence=evidence,
        progression=_progression(admission, evidence),
        transition_cause="LATER_EXPLICIT_FAILURE",
        qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
        observed_at=evidence.candle_end + timedelta(seconds=1),
    )
    failed = bind_cycle_evaluation(
        cycle=qualified.cycle, observation=observation, transition=transition
    )
    second = create_wo15_timing_handoff(
        admission=admission,
        evaluation=failed,
        predecessor=first,
        handoff_created_at=observation.observed_at + timedelta(seconds=1),
        supersession_lineage_identity="WO15-HANDOFF-SUPERSESSION-LINEAGE",
    )
    assert first.current_state is Wo15TimingState.TIMING_QUALIFIED
    assert second.current_state is Wo15TimingState.TIMING_FAILED
    assert second.predecessor_handoff_identity == first.handoff_identity


def test_handoff_identity_determinism_and_corruption_fail_closed(tmp_path) -> None:
    admission, _, _, _, unavailable = _evaluation(
        tmp_path, state=Wo15TimingState.TIMING_UNAVAILABLE
    )
    created = unavailable.observation.observed_at + timedelta(seconds=1)
    first = create_wo15_timing_handoff(
        admission=admission, evaluation=unavailable, handoff_created_at=created
    )
    second = create_wo15_timing_handoff(
        admission=admission, evaluation=unavailable, handoff_created_at=created
    )
    assert first == second
    with pytest.raises(Wo15ContractError, match="WO15_TIMING_HANDOFF_INVALID"):
        replace(first, handoff_integrity="CORRUPT")


def test_trust_failure_handoff_remains_unavailable_not_failed(tmp_path) -> None:
    _, _, _, _, unavailable = _evaluation(
        tmp_path, state=Wo15TimingState.TIMING_UNAVAILABLE
    )
    assert unavailable.transition.trust_failure is Wo15TrustFailure.SOURCE_EVIDENCE_INVALID
    assert unavailable.transition.current_state is Wo15TimingState.TIMING_UNAVAILABLE
    assert unavailable.transition.current_state is not Wo15TimingState.TIMING_FAILED
