from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import (
    SemanticDirection,
    create_governed_historical_candle_payload,
)
from kronos.intraday.probables_v2 import (
    SEMANTIC_FACT_V2_IDENTITY,
    V2_CONTRACT_VERSION,
    SemanticEvidenceRoleV2,
    SemanticQualificationFactV2,
    _identity as _probables_identity,
)
from kronos.intraday.wo12_k5_foundation import Wo12SetupFamily
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo15 import (
    WO15_POLICY_CHECKSUM,
    Wo15AdmissionRejected,
    Wo15ExpiryCause,
    Wo15ProgressionSemantics,
    Wo15QualificationPath,
    Wo15TimingState,
    Wo15TrustFailure,
    adapt_five_minute_progression,
    bind_completed_five_minute_evidence,
)
from kronos.intraday.wo15_timing import (
    WO15_RESET_ASSESSMENT_IDENTITY,
    WO15_TIMING_EVALUATOR_IDENTITY,
    WO15_TIMING_GRAMMAR_VERSION,
    WO15_TIMING_HISTORY_IDENTITY,
    WO15_TIMING_RESULT_IDENTITY,
    Wo15ResetDisposition,
    Wo15TimingCause,
    Wo15TimingGrammarError,
    create_wo15_expiry_event,
    evaluate_wo15_successor_cycle,
    evaluate_wo15_timing,
)

from .test_wo13_contracts import _handoff
from .test_wo15_contracts import (
    _mcx_wo13,
    _session,
    _wo13_from_handoff,
)


def _case(
    tmp_path: Path,
    *,
    setup: Wo12SetupFamily = Wo12SetupFamily.PULLBACK_CONTINUATION,
    direction: SemanticDirection = SemanticDirection.LONG,
):  # type: ignore[no-untyped-def]
    source_handoff = _handoff(tmp_path, setup=setup, direction=direction)
    *_, admission = _wo13_from_handoff(source_handoff)
    return admission, _session(admission)


def _candle(
    admission,  # type: ignore[no-untyped-def]
    session,  # type: ignore[no-untyped-def]
    *,
    minute: int,
    open: str | None = None,
    high: str = "101",
    low: str = "99",
    close: str = "100",
    end=None,  # type: ignore[no-untyped-def]
    exchange: str | None = None,
    instrument_identity: str | None = None,
    actual_contract_identity: str | None = None,
    roll_lineage_identity: str | None = None,
):
    candle_end = end or admission.analysis_boundary + timedelta(minutes=minute)
    candle_start = candle_end - timedelta(minutes=5)
    actual_exchange = exchange or (
        "MCX" if admission.market_family.value == "MCX" else "NSE"
    )
    source = create_governed_historical_candle_payload(
        canonical_subject_identity=admission.canonical_subject_identity,
        exchange=actual_exchange,
        market_identity=actual_exchange,
        market_session_identity=session.session_identity,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        candle_start=candle_start,
        candle_end=candle_end,
        open=Decimal(close if open is None else open),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=100,
        observation_boundary=candle_end,
        provider_source_identity="GOVERNED-WO15B-EVIDENCE",
        source_operation_identity=f"WO15B-ISOLATED-{minute}",
        provenance=("WO-15B",),
    )
    evidence = bind_completed_five_minute_evidence(
        source=source,
        market_family=admission.market_family,
        instrument_identity=instrument_identity or admission.instrument_identity,
        actual_contract_identity=(
            admission.actual_contract_identity
            if actual_contract_identity is None
            else actual_contract_identity
        ),
        roll_lineage_identity=(
            admission.roll_lineage_identity
            if roll_lineage_identity is None
            else roll_lineage_identity
        ),
    )
    return source, evidence


def _progression(
    admission,  # type: ignore[no-untyped-def]
    evidence,  # type: ignore[no-untyped-def]
    semantics: Wo15ProgressionSemantics,
):
    direction = {
        Wo15ProgressionSemantics.ALIGNED: admission.direction,
        Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING: (
            SemanticDirection.NON_DIRECTIONAL
        ),
        Wo15ProgressionSemantics.CONTRADICTORY: (
            SemanticDirection.SHORT
            if admission.direction is SemanticDirection.LONG
            else SemanticDirection.LONG
        ),
        Wo15ProgressionSemantics.UNAVAILABLE: SemanticDirection.UNAVAILABLE,
    }[semantics]
    values = {
        "family": "5M_PROGRESSION",
        "canonical_subject_identity": admission.canonical_subject_identity,
        "analysis_boundary": evidence.observation_boundary,
        "phase": IntradayAnalysisPhase.STRUCTURE,
        "availability": (
            "UNAVAILABLE"
            if semantics is Wo15ProgressionSemantics.UNAVAILABLE
            else "AVAILABLE"
        ),
        "direction": direction,
        "evidence_role": SemanticEvidenceRoleV2.OPENING_CONFLICT_INPUT,
        "source_evidence_identities": (evidence.source_candle_identity,),
        "attributes": (("relationship", "GOVERNED_EXISTING_FACT"),),
        "schema_identity": SEMANTIC_FACT_V2_IDENTITY,
        "schema_version": V2_CONTRACT_VERSION,
    }
    fact = SemanticQualificationFactV2(
        fact_identity=_probables_identity("INTRADAY-SEMANTIC-V2-FACT-", values),
        integrity_identity=_probables_identity(
            "INTEGRITY-INTRADAY-SEMANTIC-V2-FACT-", values
        ),
        **values,
    )
    return adapt_five_minute_progression(
        fact, inherited_direction=admission.direction
    )


def _evaluate(
    admission,  # type: ignore[no-untyped-def]
    session,  # type: ignore[no-untyped-def]
    *,
    minute: int,
    close: str,
    semantics: Wo15ProgressionSemantics,
    previous=None,  # type: ignore[no-untyped-def]
    open: str | None = None,
    high: str = "101",
    low: str = "99",
    end=None,  # type: ignore[no-untyped-def]
    expiry_event=None,  # type: ignore[no-untyped-def]
    **contexts,
):
    source, evidence = _candle(
        admission,
        session,
        minute=minute,
        open=open,
        high=high,
        low=low,
        close=close,
        end=end,
    )
    progression = _progression(admission, evidence, semantics)
    result = evaluate_wo15_timing(
        admission=admission,
        session=session,
        source_candle=source,
        evidence=evidence,
        progression=progression,
        previous=previous,
        observed_at=evidence.candle_end + timedelta(seconds=1),
        expiry_event=expiry_event,
        **contexts,
    )
    return source, evidence, progression, result


def test_contract_identity_policy_and_negative_authorities() -> None:
    assert WO15_TIMING_EVALUATOR_IDENTITY == (
        "KRONOS-INTRADAY-WO15-TIMING-EVALUATOR-V1"
    )
    assert WO15_TIMING_GRAMMAR_VERSION == "1.0.0"
    assert WO15_TIMING_RESULT_IDENTITY.endswith("TIMING-EVALUATION-RESULT-V1")
    assert WO15_TIMING_HISTORY_IDENTITY.endswith("TIMING-LOCAL-HISTORY-V1")
    assert WO15_RESET_ASSESSMENT_IDENTITY.endswith("RESET-ASSESSMENT-V1")
    assert WO15_POLICY_CHECKSUM == (
        "d36386a98e2f1b78e5b70d0c27079c056951fd76a5b70ec2e9fa1bc1615a3f26"
    )


@pytest.mark.parametrize(
    ("direction", "close"),
    ((SemanticDirection.LONG, "100.01"), (SemanticDirection.SHORT, "99.99")),
)
def test_pullback_one_strict_aligned_close_qualifies(tmp_path, direction, close) -> None:
    admission, session = _case(tmp_path, direction=direction)
    *_, result = _evaluate(
        admission,
        session,
        minute=5,
        close=close,
        semantics=Wo15ProgressionSemantics.ALIGNED,
        high="101" if direction is SemanticDirection.LONG else "101",
        low="99",
    )
    assert result.current_state is Wo15TimingState.TIMING_QUALIFIED
    assert result.qualification_path is Wo15QualificationPath.PULLBACK_CONTINUATION
    assert result.transition_created
    assert result.local_history.first_qualification_boundary == result.observation_boundary


@pytest.mark.parametrize("direction", (SemanticDirection.LONG, SemanticDirection.SHORT))
def test_pullback_equality_and_forming_remain_waiting(tmp_path, direction) -> None:
    admission, session = _case(tmp_path, direction=direction)
    *_, equality = _evaluate(
        admission,
        session,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.ALIGNED,
    )
    assert equality.current_state is Wo15TimingState.TIMING_WAITING
    beyond = "101" if direction is SemanticDirection.LONG else "99"
    *_, forming = _evaluate(
        admission,
        session,
        minute=5,
        close=beyond,
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
        high="102",
        low="98",
    )
    assert forming.current_state is Wo15TimingState.TIMING_WAITING


@pytest.mark.parametrize("direction", (SemanticDirection.LONG, SemanticDirection.SHORT))
def test_pullback_opposing_progression_fails_before_or_after_qualification(
    tmp_path, direction
) -> None:
    admission, session = _case(tmp_path, direction=direction)
    *_, failed = _evaluate(
        admission,
        session,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.CONTRADICTORY,
    )
    assert failed.current_state is Wo15TimingState.TIMING_FAILED
    assert failed.cause is Wo15TimingCause.PULLBACK_OPPOSING_PROGRESSION
    qualified_close = "101" if direction is SemanticDirection.LONG else "99"
    *_, qualified = _evaluate(
        admission,
        session,
        minute=10,
        close=qualified_close,
        semantics=Wo15ProgressionSemantics.ALIGNED,
        high="102",
        low="98",
    )
    qualification_boundary = qualified.local_history.first_qualification_boundary
    *_, later_failed = _evaluate(
        admission,
        session,
        minute=15,
        close=qualified_close,
        semantics=Wo15ProgressionSemantics.CONTRADICTORY,
        previous=qualified,
        high="102",
        low="98",
    )
    assert later_failed.current_state is Wo15TimingState.TIMING_FAILED
    assert later_failed.local_history.first_qualification_boundary == qualification_boundary
    assert later_failed.local_history.failure_boundary == later_failed.observation_boundary


@pytest.mark.parametrize(
    ("direction", "close"),
    ((SemanticDirection.LONG, "100.01"), (SemanticDirection.SHORT, "99.99")),
)
def test_breakout_direct_acceptance_is_symmetric(tmp_path, direction, close) -> None:
    admission, session = _case(
        tmp_path, setup=Wo12SetupFamily.RANGE_BREAKOUT, direction=direction
    )
    *_, result = _evaluate(
        admission,
        session,
        minute=5,
        close=close,
        semantics=Wo15ProgressionSemantics.ALIGNED,
    )
    assert result.current_state is Wo15TimingState.TIMING_QUALIFIED
    assert result.qualification_path is Wo15QualificationPath.DIRECT_ACCEPTANCE


@pytest.mark.parametrize("direction", (SemanticDirection.LONG, SemanticDirection.SHORT))
def test_breakout_equality_neither_qualifies_nor_fails(tmp_path, direction) -> None:
    admission, session = _case(
        tmp_path, setup=Wo12SetupFamily.RANGE_BREAKOUT, direction=direction
    )
    *_, first = _evaluate(
        admission,
        session,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    *_, second = _evaluate(
        admission,
        session,
        minute=10,
        close="100",
        semantics=Wo15ProgressionSemantics.ALIGNED,
        previous=first,
    )
    assert first.current_state is Wo15TimingState.TIMING_WAITING
    assert second.current_state is Wo15TimingState.TIMING_WAITING


def test_long_breakout_retest_requires_prior_acceptance_and_resumes(tmp_path) -> None:
    admission, session = _case(tmp_path, setup=Wo12SetupFamily.RANGE_BREAKOUT)
    *_, no_prior = _evaluate(
        admission,
        session,
        minute=5,
        close="100",
        low="99.5",
        high="101",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    assert no_prior.local_history.retest_evidence_identity is None
    *_, accepted = _evaluate(
        admission,
        session,
        minute=10,
        close="100.50",
        high="101",
        low="100.10",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
        previous=no_prior,
    )
    *_, retest = _evaluate(
        admission,
        session,
        minute=15,
        close="100",
        high="101",
        low="99.5",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
        previous=accepted,
    )
    assert retest.current_state is Wo15TimingState.TIMING_WAITING
    assert retest.cause is Wo15TimingCause.BREAKOUT_RETEST_RECORDED
    assert retest.local_history.retest_high == Decimal("101")
    *_, resumed = _evaluate(
        admission,
        session,
        minute=20,
        close="101.01",
        high="102",
        low="100.5",
        semantics=Wo15ProgressionSemantics.ALIGNED,
        previous=retest,
    )
    assert resumed.current_state is Wo15TimingState.TIMING_QUALIFIED
    assert resumed.qualification_path is Wo15QualificationPath.RETEST_RESUMPTION
    assert resumed.local_history.retest_evidence_identity == (
        retest.local_history.retest_evidence_identity
    )


def test_short_breakout_retest_and_resumption_are_symmetric(tmp_path) -> None:
    admission, session = _case(
        tmp_path,
        setup=Wo12SetupFamily.RANGE_BREAKOUT,
        direction=SemanticDirection.SHORT,
    )
    *_, accepted = _evaluate(
        admission,
        session,
        minute=5,
        close="99.5",
        high="99.9",
        low="99",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    *_, retest = _evaluate(
        admission,
        session,
        minute=10,
        close="100",
        high="100.5",
        low="99",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
        previous=accepted,
    )
    assert retest.local_history.retest_low == Decimal("99")
    *_, resumed = _evaluate(
        admission,
        session,
        minute=15,
        close="98.99",
        high="99.5",
        low="98",
        semantics=Wo15ProgressionSemantics.ALIGNED,
        previous=retest,
    )
    assert resumed.current_state is Wo15TimingState.TIMING_QUALIFIED
    assert resumed.qualification_path is Wo15QualificationPath.RETEST_RESUMPTION


def test_retest_path_cannot_fall_back_to_direct_acceptance(tmp_path) -> None:
    admission, session = _case(tmp_path, setup=Wo12SetupFamily.RANGE_BREAKOUT)
    *_, accepted = _evaluate(
        admission,
        session,
        minute=5,
        close="100.5",
        high="101",
        low="100.1",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    *_, retest = _evaluate(
        admission,
        session,
        minute=10,
        close="100",
        high="102",
        low="99.5",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
        previous=accepted,
    )
    *_, not_resumed = _evaluate(
        admission,
        session,
        minute=15,
        close="101",
        high="101.5",
        low="100.5",
        semantics=Wo15ProgressionSemantics.ALIGNED,
        previous=retest,
    )
    assert not_resumed.current_state is Wo15TimingState.TIMING_WAITING
    assert not_resumed.qualification_path is Wo15QualificationPath.NOT_APPLICABLE


@pytest.mark.parametrize(
    ("direction", "inside"),
    ((SemanticDirection.LONG, "99.99"), (SemanticDirection.SHORT, "100.01")),
)
def test_breakout_failure_requires_prior_completed_interaction(
    tmp_path, direction, inside
) -> None:
    admission, session = _case(
        tmp_path, setup=Wo12SetupFamily.RANGE_BREAKOUT, direction=direction
    )
    *_, before = _evaluate(
        admission,
        session,
        minute=5,
        close=inside,
        high="99.99" if direction is SemanticDirection.LONG else "101",
        low="99" if direction is SemanticDirection.LONG else "100.01",
        semantics=Wo15ProgressionSemantics.ALIGNED,
    )
    assert before.current_state is Wo15TimingState.TIMING_WAITING
    *_, interaction = _evaluate(
        admission,
        session,
        minute=10,
        close="100",
        high="101",
        low="99",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
        previous=before,
    )
    *_, failed = _evaluate(
        admission,
        session,
        minute=15,
        close=inside,
        high="101",
        low="99",
        semantics=Wo15ProgressionSemantics.ALIGNED,
        previous=interaction,
    )
    assert failed.current_state is Wo15TimingState.TIMING_FAILED
    assert failed.cause is Wo15TimingCause.BREAKOUT_RETURNED_INSIDE_RANGE


def test_qualified_state_does_not_flicker_and_later_failure_is_append_only(tmp_path) -> None:
    admission, session = _case(tmp_path, setup=Wo12SetupFamily.RANGE_BREAKOUT)
    *_, qualified = _evaluate(
        admission,
        session,
        minute=5,
        close="101",
        high="102",
        low="100.5",
        semantics=Wo15ProgressionSemantics.ALIGNED,
    )
    first_transition = qualified.cycle_evaluation.transition.transition_identity
    first_qualification = qualified.local_history.first_qualification_boundary
    *_, retained = _evaluate(
        admission,
        session,
        minute=10,
        close="100.5",
        high="101",
        low="100.1",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
        previous=qualified,
    )
    assert retained.current_state is Wo15TimingState.TIMING_QUALIFIED
    assert not retained.transition_created
    assert retained.cycle_evaluation.transition.transition_identity == first_transition
    *_, failed = _evaluate(
        admission,
        session,
        minute=15,
        close="99.99",
        high="100.5",
        low="99",
        semantics=Wo15ProgressionSemantics.ALIGNED,
        previous=retained,
    )
    assert failed.current_state is Wo15TimingState.TIMING_FAILED
    assert failed.local_history.first_qualification_boundary == first_qualification
    assert failed.cycle_evaluation.transition.transition_identity != first_transition


def test_session_end_and_explicit_supersession_expire_active_cycle(tmp_path) -> None:
    admission, session = _case(tmp_path)
    *_, waiting = _evaluate(
        admission,
        session,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    final_end = session.session_closes_at
    *_, expired = _evaluate(
        admission,
        session,
        minute=10,
        end=final_end,
        close="101",
        high="102",
        low="100",
        semantics=Wo15ProgressionSemantics.ALIGNED,
        previous=waiting,
    )
    assert expired.current_state is Wo15TimingState.TIMING_EXPIRED
    assert expired.expiry_cause is Wo15ExpiryCause.SESSION_END
    assert expired.local_history.expiry_at == final_end

    admission_two, session_two = _case(tmp_path / "superseded")
    *_, waiting_two = _evaluate(
        admission_two,
        session_two,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    source, evidence = _candle(
        admission_two, session_two, minute=10, close="101", high="102", low="100"
    )
    event = create_wo15_expiry_event(
        cause=Wo15ExpiryCause.WO13_PLAN_SUPERSEDED,
        event_boundary=evidence.candle_end,
        source_identity="CURRENT-WO13-POINTER",
        source_integrity="CURRENT-WO13-POINTER-INTEGRITY",
        admission=admission_two,
        session=session_two,
    )
    explicit = evaluate_wo15_timing(
        admission=admission_two,
        session=session_two,
        source_candle=source,
        evidence=evidence,
        progression=_progression(
            admission_two, evidence, Wo15ProgressionSemantics.CONTRADICTORY
        ),
        observed_at=evidence.candle_end + timedelta(seconds=1),
        previous=waiting_two,
        expiry_event=event,
    )
    assert explicit.current_state is Wo15TimingState.TIMING_EXPIRED
    assert explicit.expiry_cause is Wo15ExpiryCause.WO13_PLAN_SUPERSEDED


@pytest.mark.parametrize(
    "cause",
    (
        Wo15ExpiryCause.UPSTREAM_CYCLE_SUPERSEDED,
        Wo15ExpiryCause.INSTRUMENT_CONTRACT_SUPERSEDED,
        Wo15ExpiryCause.DOMAIN008_SESSION_INVALID,
    ),
)
def test_all_governed_expiry_causes_have_precedence(tmp_path, cause) -> None:
    admission, session = _case(tmp_path)
    *_, waiting = _evaluate(
        admission,
        session,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    source, evidence = _candle(
        admission, session, minute=10, close="101", high="102", low="100"
    )
    event = create_wo15_expiry_event(
        cause=cause,
        event_boundary=evidence.candle_end,
        source_identity=f"EXPIRY-{cause.value}",
        source_integrity=f"INTEGRITY-{cause.value}",
        admission=admission,
        session=session,
    )
    result = evaluate_wo15_timing(
        admission=admission,
        session=session,
        source_candle=source,
        evidence=evidence,
        progression=_progression(
            admission, evidence, Wo15ProgressionSemantics.CONTRADICTORY
        ),
        observed_at=evidence.candle_end + timedelta(seconds=1),
        previous=waiting,
        expiry_event=event,
    )
    assert result.current_state is Wo15TimingState.TIMING_EXPIRED
    assert result.expiry_cause is cause


def test_unavailable_is_not_failed_for_missing_or_unavailable_evidence(tmp_path) -> None:
    admission, session = _case(tmp_path)
    source, evidence = _candle(admission, session, minute=5)
    unavailable = evaluate_wo15_timing(
        admission=admission,
        session=session,
        source_candle=source,
        evidence=evidence,
        progression=_progression(
            admission, evidence, Wo15ProgressionSemantics.UNAVAILABLE
        ),
        observed_at=evidence.candle_end + timedelta(seconds=1),
    )
    assert unavailable.current_state is Wo15TimingState.TIMING_UNAVAILABLE
    assert (
        unavailable.trust_failure
        is Wo15TrustFailure.UPSTREAM_COMMISSIONING_UNAVAILABLE
    )
    assert unavailable.transition_created
    missing = evaluate_wo15_timing(
        admission=admission,
        session=session,
        source_candle=None,
        evidence=evidence,
        progression=_progression(
            admission, evidence, Wo15ProgressionSemantics.ALIGNED
        ),
        observed_at=evidence.candle_end + timedelta(seconds=1),
    )
    assert missing.current_state is Wo15TimingState.TIMING_UNAVAILABLE
    assert missing.trust_failure is Wo15TrustFailure.FIVE_MINUTE_EVIDENCE_INCOMPLETE
    assert not missing.transition_created


def test_waiting_to_unavailable_transition_and_precedence_over_expiry(tmp_path) -> None:
    admission, session = _case(tmp_path)
    *_, waiting = _evaluate(
        admission,
        session,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    source, evidence = _candle(admission, session, minute=10, close="101")
    event = create_wo15_expiry_event(
        cause=Wo15ExpiryCause.WO13_PLAN_SUPERSEDED,
        event_boundary=evidence.candle_end,
        source_identity="CURRENT-WO13-POINTER",
        source_integrity="CURRENT-WO13-POINTER-INTEGRITY",
        admission=admission,
        session=session,
    )
    unavailable = evaluate_wo15_timing(
        admission=admission,
        session=session,
        source_candle=source,
        evidence=evidence,
        progression=_progression(
            admission, evidence, Wo15ProgressionSemantics.UNAVAILABLE
        ),
        observed_at=evidence.candle_end + timedelta(seconds=1),
        previous=waiting,
        expiry_event=event,
    )
    assert unavailable.prior_state is Wo15TimingState.TIMING_WAITING
    assert unavailable.current_state is Wo15TimingState.TIMING_UNAVAILABLE
    assert unavailable.expiry_cause is None
    assert unavailable.transition_created


def _failed_pullback(tmp_path: Path):
    admission, session = _case(tmp_path)
    source, evidence, progression, failed = _evaluate(
        admission,
        session,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.CONTRADICTORY,
    )
    return admission, session, source, evidence, progression, failed


def test_pullback_reset_waiting_and_immediate_qualification(tmp_path) -> None:
    admission, session, *_, failed = _failed_pullback(tmp_path)
    source, evidence = _candle(admission, session, minute=10, close="99")
    progression = _progression(
        admission, evidence, Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING
    )
    assessment, waiting = evaluate_wo15_successor_cycle(
        admission=admission,
        session=session,
        predecessor=failed,
        source_candle=source,
        evidence=evidence,
        progression=progression,
        observed_at=evidence.candle_end + timedelta(seconds=1),
    )
    assert assessment.eligible
    assert waiting.current_state is Wo15TimingState.TIMING_WAITING
    assert waiting.cycle_evaluation.cycle.cycle_ordinal == 2
    assert waiting.cycle_evaluation.cycle.predecessor_cycle_identity == (
        failed.cycle_evaluation.cycle.timing_cycle_id
    )

    admission_two, session_two, *_, failed_two = _failed_pullback(tmp_path / "q")
    source_two, evidence_two = _candle(
        admission_two, session_two, minute=10, close="101", high="102", low="100"
    )
    assessment_two, qualified = evaluate_wo15_successor_cycle(
        admission=admission_two,
        session=session_two,
        predecessor=failed_two,
        source_candle=source_two,
        evidence=evidence_two,
        progression=_progression(
            admission_two, evidence_two, Wo15ProgressionSemantics.ALIGNED
        ),
        observed_at=evidence_two.candle_end + timedelta(seconds=1),
    )
    assert assessment_two.eligible
    assert qualified.current_state is Wo15TimingState.TIMING_QUALIFIED


@pytest.mark.parametrize(
    ("direction", "reset_close", "qualified_close"),
    (
        (SemanticDirection.LONG, "100", "100.01"),
        (SemanticDirection.SHORT, "100", "99.99"),
    ),
)
def test_breakout_reset_boundary_and_immediate_qualification(
    tmp_path, direction, reset_close, qualified_close
) -> None:
    admission, session = _case(
        tmp_path, setup=Wo12SetupFamily.RANGE_BREAKOUT, direction=direction
    )
    *_, interaction = _evaluate(
        admission,
        session,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    inside = "99.99" if direction is SemanticDirection.LONG else "100.01"
    *_, failed = _evaluate(
        admission,
        session,
        minute=10,
        close=inside,
        semantics=Wo15ProgressionSemantics.ALIGNED,
        previous=interaction,
    )
    source, evidence = _candle(admission, session, minute=15, close=reset_close)
    assessment, waiting = evaluate_wo15_successor_cycle(
        admission=admission,
        session=session,
        predecessor=failed,
        source_candle=source,
        evidence=evidence,
        progression=_progression(
            admission, evidence, Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING
        ),
        observed_at=evidence.candle_end + timedelta(seconds=1),
    )
    assert assessment.eligible and waiting.current_state is Wo15TimingState.TIMING_WAITING

    admission_q, session_q = _case(
        tmp_path / "q", setup=Wo12SetupFamily.RANGE_BREAKOUT, direction=direction
    )
    *_, interaction_q = _evaluate(
        admission_q,
        session_q,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    *_, failed_q = _evaluate(
        admission_q,
        session_q,
        minute=10,
        close=inside,
        semantics=Wo15ProgressionSemantics.ALIGNED,
        previous=interaction_q,
    )
    source_q, evidence_q = _candle(
        admission_q, session_q, minute=15, close=qualified_close
    )
    assessment_q, qualified = evaluate_wo15_successor_cycle(
        admission=admission_q,
        session=session_q,
        predecessor=failed_q,
        source_candle=source_q,
        evidence=evidence_q,
        progression=_progression(
            admission_q, evidence_q, Wo15ProgressionSemantics.ALIGNED
        ),
        observed_at=evidence_q.candle_end + timedelta(seconds=1),
    )
    assert assessment_q.eligible
    assert qualified.current_state is Wo15TimingState.TIMING_QUALIFIED


def test_reset_rejects_early_contradictory_nonterminal_expired_and_foreign(tmp_path) -> None:
    admission, session, *_, failed = _failed_pullback(tmp_path)
    source, evidence = _candle(admission, session, minute=5, close="101")
    assessment, result = evaluate_wo15_successor_cycle(
        admission=admission,
        session=session,
        predecessor=failed,
        source_candle=source,
        evidence=evidence,
        progression=_progression(
            admission, evidence, Wo15ProgressionSemantics.ALIGNED
        ),
        observed_at=evidence.candle_end + timedelta(seconds=1),
    )
    assert assessment.disposition is Wo15ResetDisposition.BOUNDARY_NOT_LATER
    assert result is None

    source_later, evidence_later = _candle(admission, session, minute=10)
    contradictory, result = evaluate_wo15_successor_cycle(
        admission=admission,
        session=session,
        predecessor=failed,
        source_candle=source_later,
        evidence=evidence_later,
        progression=_progression(
            admission, evidence_later, Wo15ProgressionSemantics.CONTRADICTORY
        ),
        observed_at=evidence_later.candle_end + timedelta(seconds=1),
    )
    assert contradictory.disposition is Wo15ResetDisposition.PROGRESSION_CONTRADICTORY
    assert result is None

    admission_w, session_w = _case(tmp_path / "waiting")
    *_, waiting = _evaluate(
        admission_w,
        session_w,
        minute=5,
        close="100",
        semantics=Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
    )
    source_w, evidence_w = _candle(admission_w, session_w, minute=10)
    nonterminal, result = evaluate_wo15_successor_cycle(
        admission=admission_w,
        session=session_w,
        predecessor=waiting,
        source_candle=source_w,
        evidence=evidence_w,
        progression=_progression(
            admission_w, evidence_w, Wo15ProgressionSemantics.ALIGNED
        ),
        observed_at=evidence_w.candle_end + timedelta(seconds=1),
    )
    assert nonterminal.disposition is Wo15ResetDisposition.PRIOR_CYCLE_NOT_FAILED
    assert result is None

    source_end, evidence_end = _candle(
        admission, session, minute=15, end=session.session_closes_at
    )
    expired, result = evaluate_wo15_successor_cycle(
        admission=admission,
        session=session,
        predecessor=failed,
        source_candle=source_end,
        evidence=evidence_end,
        progression=_progression(
            admission, evidence_end, Wo15ProgressionSemantics.ALIGNED
        ),
        observed_at=evidence_end.candle_end + timedelta(seconds=1),
    )
    assert expired.disposition is Wo15ResetDisposition.SESSION_OR_LINEAGE_EXPIRED
    assert result is None

    foreign_admission, foreign_session = _case(
        tmp_path / "foreign", direction=SemanticDirection.SHORT
    )
    foreign_source, foreign_evidence = _candle(
        foreign_admission, foreign_session, minute=10
    )
    foreign, result = evaluate_wo15_successor_cycle(
        admission=foreign_admission,
        session=foreign_session,
        predecessor=failed,
        source_candle=foreign_source,
        evidence=foreign_evidence,
        progression=_progression(
            foreign_admission,
            foreign_evidence,
            Wo15ProgressionSemantics.ALIGNED,
        ),
        observed_at=foreign_evidence.candle_end + timedelta(seconds=1),
    )
    assert foreign.disposition is Wo15ResetDisposition.TRUST_UNAVAILABLE
    assert result is None


def test_multiple_failed_successor_cycles_have_no_arbitrary_maximum(tmp_path) -> None:
    admission, session, *_, cycle_one = _failed_pullback(tmp_path)
    source_two, evidence_two = _candle(admission, session, minute=10, close="99")
    _, cycle_two = evaluate_wo15_successor_cycle(
        admission=admission,
        session=session,
        predecessor=cycle_one,
        source_candle=source_two,
        evidence=evidence_two,
        progression=_progression(
            admission, evidence_two, Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING
        ),
        observed_at=evidence_two.candle_end + timedelta(seconds=1),
    )
    *_, cycle_two_failed = _evaluate(
        admission,
        session,
        minute=15,
        close="99",
        semantics=Wo15ProgressionSemantics.CONTRADICTORY,
        previous=cycle_two,
    )
    source_three, evidence_three = _candle(admission, session, minute=20, close="99")
    _, cycle_three = evaluate_wo15_successor_cycle(
        admission=admission,
        session=session,
        predecessor=cycle_two_failed,
        source_candle=source_three,
        evidence=evidence_three,
        progression=_progression(
            admission,
            evidence_three,
            Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING,
        ),
        observed_at=evidence_three.candle_end + timedelta(seconds=1),
    )
    assert cycle_three.cycle_evaluation.cycle.cycle_ordinal == 3
    assert cycle_three.cycle_evaluation.cycle.predecessor_cycle_identity == (
        cycle_two_failed.cycle_evaluation.cycle.timing_cycle_id
    )


def test_ltp_risk_rr_and_research_telemetry_have_no_authority(tmp_path) -> None:
    admission, session = _case(tmp_path)
    source, evidence = _candle(admission, session, minute=5, close="100")
    progression = _progression(
        admission, evidence, Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING
    )
    baseline = evaluate_wo15_timing(
        admission=admission,
        session=session,
        source_candle=source,
        evidence=evidence,
        progression=progression,
        observed_at=evidence.candle_end + timedelta(seconds=1),
    )
    contextual = evaluate_wo15_timing(
        admission=admission,
        session=session,
        source_candle=source,
        evidence=evidence,
        progression=progression,
        observed_at=evidence.candle_end + timedelta(seconds=1),
        wo14_reference_state="RISK_ALERT",
        model_rr_context=Decimal("0.01"),
    )
    assert contextual == baseline
    source_text = Path("src/kronos/intraday/wo15_timing.py").read_text()
    for prohibited in (
        "live_ltp",
        "calculate_atr",
        "rsi_value",
        "railway_value",
        "sma20",
        "class Wo15Store",
        "IntradayWo15Application",
        "FastAPI",
        "HTTPServer",
    ):
        assert prohibited.lower() not in source_text.lower()


def test_wick_only_does_not_qualify_but_records_local_interaction(tmp_path) -> None:
    admission, session = _case(tmp_path)
    *_, result = _evaluate(
        admission,
        session,
        minute=5,
        close="99.5",
        high="101",
        low="99",
        semantics=Wo15ProgressionSemantics.ALIGNED,
    )
    assert result.current_state is Wo15TimingState.TIMING_WAITING
    assert result.local_history.first_entry_interaction_boundary == (
        result.observation_boundary
    )


def test_mcx_exact_contract_and_reference_market_fail_closed(tmp_path) -> None:
    *_, admission = _mcx_wo13(tmp_path)
    session = _session(admission)
    source, evidence = _candle(admission, session, minute=5, close="101")
    accepted = evaluate_wo15_timing(
        admission=admission,
        session=session,
        source_candle=source,
        evidence=evidence,
        progression=_progression(
            admission, evidence, Wo15ProgressionSemantics.ALIGNED
        ),
        observed_at=evidence.candle_end + timedelta(seconds=1),
    )
    assert accepted.current_state is Wo15TimingState.TIMING_QUALIFIED
    with pytest.raises(Wo15AdmissionRejected, match="FIVE_MINUTE_EVIDENCE_INCOMPLETE"):
        _candle(
            admission,
            session,
            minute=10,
            exchange="COMEX",
            close="101",
        )
    foreign, foreign_evidence = _candle(
        admission,
        session,
        minute=10,
        actual_contract_identity="MCX-FUT-GOLDM-FOREIGN",
        close="101",
    )
    unavailable = evaluate_wo15_timing(
        admission=admission,
        session=session,
        source_candle=foreign,
        evidence=foreign_evidence,
        progression=_progression(
            admission, foreign_evidence, Wo15ProgressionSemantics.ALIGNED
        ),
        observed_at=foreign_evidence.candle_end + timedelta(seconds=1),
    )
    assert unavailable.current_state is Wo15TimingState.TIMING_UNAVAILABLE
    assert unavailable.trust_failure is Wo15TrustFailure.ACTIVE_CONTRACT_MISMATCH


def test_determinism_material_change_integrity_and_terminal_behavior(tmp_path) -> None:
    admission, session = _case(tmp_path)
    args = dict(
        admission=admission,
        session=session,
        minute=5,
        close="101",
        semantics=Wo15ProgressionSemantics.ALIGNED,
    )
    *_, first = _evaluate(**args)
    *_, same = _evaluate(**args)
    assert same == first
    *_, changed = _evaluate(
        admission,
        session,
        minute=5,
        close="100.99",
        high="101",
        semantics=Wo15ProgressionSemantics.ALIGNED,
    )
    assert changed.result_identity != first.result_identity
    with pytest.raises(Wo15TimingGrammarError, match="WO15_TIMING_RESULT_INVALID"):
        replace(first, result_integrity="CORRUPT")
    admission_f, session_f, *_, failed = _failed_pullback(tmp_path / "terminal")
    source_f, evidence_f = _candle(admission_f, session_f, minute=10)
    with pytest.raises(
        Wo15TimingGrammarError,
        match="WO15_TERMINAL_CYCLE_REEVALUATION_PROHIBITED",
    ):
        evaluate_wo15_timing(
            admission=admission_f,
            session=session_f,
            source_candle=source_f,
            evidence=evidence_f,
            progression=_progression(
                admission_f, evidence_f, Wo15ProgressionSemantics.ALIGNED
            ),
            observed_at=evidence_f.candle_end + timedelta(seconds=1),
            previous=failed,
        )
