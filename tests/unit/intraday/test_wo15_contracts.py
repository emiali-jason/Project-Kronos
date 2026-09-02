from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

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
from kronos.intraday.wo13 import (
    Wo13FieldAvailability,
    Wo13GeometryAvailability,
    Wo13GeometryField,
    Wo13OperationOutcome,
    Wo13OperationStage,
    create_current_wo13_pointer,
    create_wo13_construction_request,
    create_wo13_field_availability,
    create_wo13_operation_provenance,
    create_wo13_trade_plan_contract,
)
from kronos.intraday.wo13_handoff import create_wo13_step31_handoff
from kronos.intraday.wo15 import (
    WO15_AUTHORITY,
    WO15_CONTRACT_VERSION,
    WO15_CORE_IDENTITY,
    WO15_POLICY_CHECKSUM,
    WO15_POLICY_IDENTITY,
    WO15_STATE_PRECEDENCE,
    WO15_TIMING_CYCLE_IDENTITY,
    WO15_TIMING_OBSERVATION_IDENTITY,
    WO15_TIMING_TRANSITION_IDENTITY,
    WO15_WO13_HANDOFF_IDENTITY,
    Wo15AdmissionRejected,
    Wo15ContractError,
    Wo15Wo13Handoff,
    Wo15ExpiryCause,
    Wo15PolicyBinding,
    Wo15ProgressionSemantics,
    Wo15QualificationPath,
    Wo15TimingState,
    Wo15TrustFailure,
    adapt_five_minute_progression,
    bind_completed_five_minute_evidence,
    bind_wo15_session,
    create_first_cycle_evaluation,
    create_followup_observation,
    create_successor_cycle_evaluation,
    create_wo15_wo13_handoff,
    timing_state_before_first_evaluation,
    validate_one_active_cycle,
)
from kronos.market.schedule import (
    MarketDaySchedule,
    MarketWindow,
    TradingDayStatus,
)

from .test_wo13_contracts import _handoff, _mcx_artifacts


def _wo13_from_handoff(source_handoff, *, minute: int = 30):  # type: ignore[no-untyped-def]
    request = create_wo13_construction_request(
        handoff=source_handoff,
        sponsor_operation_identity=f"SPONSOR-WO15A-{minute}",
        requested_at=source_handoff.analysis_boundary,
        provenance=("ADR-0022", "WO-15A-FIXTURE"),
    )
    availability = tuple(
        create_wo13_field_availability(
            field,
            (Wo13FieldAvailability.AVAILABLE
             if field is Wo13GeometryField.ENTRY_REFERENCE
             else Wo13FieldAvailability.UNAVAILABLE),
            reason=("GOVERNED" if field is Wo13GeometryField.ENTRY_REFERENCE
                    else "NOT_REQUIRED_FOR_WO15A_FIXTURE"),
        )
        for field in Wo13GeometryField
    )
    plan = create_wo13_trade_plan_contract(
        request=request,
        entry_reference=Decimal("100.00"),
        entry_condition=None,
        stop=None,
        stop_structural_basis=None,
        thesis_invalidation_reference=None,
        thesis_invalidation_event=None,
        setup_native_target=None,
        canonical_target=None,
        target_structural_basis=None,
        constraining_objective=None,
        risk_distance=None,
        reward_distance=None,
        model_rr=None,
        geometry_availability=Wo13GeometryAvailability.GEOMETRY_PARTIAL,
        field_availability=availability,
        warnings=(),
        supersession=None,
        provenance=("ADR-0022", "WO-15A-FIXTURE"),
    )
    operation = create_wo13_operation_provenance(
        request=request,
        stage=Wo13OperationStage.POINTER_PUBLICATION,
        outcome=Wo13OperationOutcome.COMPLETED,
        started_at=source_handoff.analysis_boundary,
        completed_at=source_handoff.analysis_boundary,
        trade_plan=plan,
        provenance=("ADR-0022", "WO-15A-FIXTURE"),
    )
    pointer = create_current_wo13_pointer(
        request=request,
        trade_plan=plan,
        operation=operation,
        published_at=source_handoff.analysis_boundary,
    )
    admission = create_wo15_wo13_handoff(
        current_pointer=pointer, trade_plan=plan, source_handoff=source_handoff
    )
    return source_handoff, request, plan, operation, pointer, admission


def _wo13(tmp_path: Path, *, minute: int = 30):  # type: ignore[no-untyped-def]
    return _wo13_from_handoff(_handoff(tmp_path, minute=minute), minute=minute)


def _mcx_wo13(tmp_path: Path):
    values = _mcx_artifacts(tmp_path)
    source_handoff = create_wo13_step31_handoff(
        current_pointer=values[0], request=values[1], evidence=values[2],
        result=values[3], eligibility=values[4], wo10_snapshot=values[5],
        setup_evidence=values[6], mcx_evidence=values[7],
    )
    return _wo13_from_handoff(source_handoff, minute=40)


def _session(admission):  # type: ignore[no-untyped-def]
    zone = ZoneInfo("Asia/Kolkata")
    day = admission.analysis_boundary.date()
    mcx = admission.market_family.value == "MCX"
    exchange = "MCX" if mcx else "NSE"
    schedule = MarketDaySchedule(
        exchange=exchange,
        trading_date=day,
        session_id=f"{exchange}-{day.isoformat()}",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(MarketWindow(
            datetime(day.year, day.month, day.day, 9, 0 if mcx else 15, tzinfo=zone),
            datetime(day.year, day.month, day.day, 23 if mcx else 15,
                     30, tzinfo=zone),
        ),),
        source_identity=f"KRONOS-{exchange}-CALENDAR-V1",
        source_version="1.0.0",
    )
    return bind_wo15_session(schedule)


def _evidence(admission, session, *, minutes_after=5, **changes):  # type: ignore[no-untyped-def]
    end = admission.analysis_boundary + timedelta(minutes=minutes_after)
    start = end - timedelta(minutes=5)
    exchange = "MCX" if admission.market_family.value == "MCX" else "NSE"
    source = create_governed_historical_candle_payload(
        canonical_subject_identity=admission.canonical_subject_identity,
        exchange=exchange,
        market_identity=exchange,
        market_session_identity=session.session_identity,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        candle_start=start,
        candle_end=end,
        open=Decimal("99"), high=Decimal("101"), low=Decimal("98"),
        close=Decimal("100"), volume=100,
        observation_boundary=end,
        provider_source_identity="GOVERNED-HISTORICAL-EVIDENCE",
        source_operation_identity="WO15A-ISOLATED-FIXTURE",
        provenance=("WO-15A",),
    )
    values = {
        "source": source,
        "market_family": admission.market_family,
        "instrument_identity": admission.instrument_identity,
        "actual_contract_identity": admission.actual_contract_identity,
        "roll_lineage_identity": admission.roll_lineage_identity,
    }
    values.update(changes)
    return bind_completed_five_minute_evidence(**values)


def _progression(admission, evidence, *, direction=None):  # type: ignore[no-untyped-def]
    values = {
        "family": "5M_PROGRESSION",
        "canonical_subject_identity": admission.canonical_subject_identity,
        "analysis_boundary": evidence.observation_boundary,
        "phase": IntradayAnalysisPhase.STRUCTURE,
        "availability": "AVAILABLE",
        "direction": direction or admission.direction,
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


def _evaluation(tmp_path, *, state=Wo15TimingState.TIMING_WAITING):  # type: ignore[no-untyped-def]
    *_, admission = _wo13(tmp_path)
    session = _session(admission)
    evidence = _evidence(admission, session)
    progression = _progression(admission, evidence)
    trust = (Wo15TrustFailure.SOURCE_EVIDENCE_INVALID
             if state is Wo15TimingState.TIMING_UNAVAILABLE else None)
    return admission, session, evidence, progression, create_first_cycle_evaluation(
        admission=admission, session=session, evidence=evidence,
        progression=progression, current_state=state,
        transition_cause="SLICE_A_CONTRACT_FIXTURE",
        qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
        cycle_created_at=evidence.candle_end + timedelta(seconds=1),
        observed_at=evidence.candle_end + timedelta(seconds=2),
        trust_failure=trust,
    )


def test_contract_identities_states_precedence_and_vocabularies_are_exact() -> None:
    assert WO15_CORE_IDENTITY == "KRONOS-INTRADAY-WO15-ENTRY-TIMING-V1"
    assert WO15_CONTRACT_VERSION == "1.0.0"
    assert WO15_AUTHORITY == "COMPLETED_5M_ENTRY_TIMING_QUALIFICATION_ONLY"
    assert WO15_WO13_HANDOFF_IDENTITY == "KRONOS-INTRADAY-WO15-WO13-HANDOFF-V1"
    assert WO15_TIMING_CYCLE_IDENTITY.endswith("TIMING-CYCLE-V1")
    assert WO15_TIMING_OBSERVATION_IDENTITY.endswith("TIMING-OBSERVATION-V1")
    assert WO15_TIMING_TRANSITION_IDENTITY.endswith("TIMING-TRANSITION-V1")
    assert tuple(item.value for item in Wo15TimingState) == (
        "TIMING_NOT_EVALUATED", "TIMING_WAITING", "TIMING_QUALIFIED",
        "TIMING_FAILED", "TIMING_EXPIRED", "TIMING_UNAVAILABLE",
    )
    assert tuple(item.value for item in WO15_STATE_PRECEDENCE) == (
        "TIMING_UNAVAILABLE", "TIMING_EXPIRED", "TIMING_FAILED",
        "TIMING_QUALIFIED", "TIMING_WAITING",
    )
    assert tuple(item.value for item in Wo15QualificationPath) == (
        "PULLBACK_CONTINUATION", "DIRECT_ACCEPTANCE",
        "RETEST_RESUMPTION", "NOT_APPLICABLE",
    )
    assert len(Wo15ExpiryCause) == 5
    assert "N_BARS_EXPIRED" not in {item.value for item in Wo15ExpiryCause}


def test_policy_is_exact_and_contains_no_downstream_authority() -> None:
    policy = Wo15PolicyBinding()
    assert (policy.policy_identity, policy.policy_checksum) == (
        WO15_POLICY_IDENTITY, WO15_POLICY_CHECKSUM
    )
    assert not any((policy.sponsor_decision_authority, policy.paper_authority,
                    policy.live_authority, policy.ignore_authority,
                    policy.position_authority, policy.broker_authority))
    with pytest.raises(Wo15ContractError, match="WO15_POLICY_BINDING_INVALID"):
        Wo15PolicyBinding(policy_checksum="0" * 64)


def test_exact_current_wo13_admission_binds_immutable_plan_and_geometry(tmp_path) -> None:
    source, _, plan, _, pointer, admission = _wo13(tmp_path)
    assert admission.wo13_trade_plan_identity == pointer.trade_plan_identity
    assert admission.wo13_trade_plan_integrity == plan.trade_plan_integrity
    assert admission.direction is plan.direction
    assert admission.setup_family is plan.setup_family
    assert admission.entry_reference == Decimal("100.00")
    assert admission.stop == plan.stop
    assert admission.canonical_target == plan.canonical_target
    assert admission.roll_lineage_identity == source.roll_lineage_identity
    assert admission == create_wo15_wo13_handoff(
        current_pointer=pointer, trade_plan=plan, source_handoff=source
    )


def test_historical_or_foreign_plan_and_integrity_fail_closed(tmp_path) -> None:
    source_a, _, plan_a, _, pointer_a, _ = _wo13(tmp_path / "a", minute=30)
    _, _, plan_b, _, _, _ = _wo13(tmp_path / "b", minute=31)
    with pytest.raises(Wo15AdmissionRejected) as rejected:
        create_wo15_wo13_handoff(
            current_pointer=pointer_a, trade_plan=plan_b, source_handoff=source_a
        )
    assert rejected.value.reason is Wo15TrustFailure.WO13_PLAN_NOT_CURRENT
    assert rejected.value.timing_state is Wo15TimingState.TIMING_UNAVAILABLE
    with pytest.raises(ValueError, match="WO13_TRADE_PLAN_INVALID"):
        replace(plan_a, trade_plan_integrity="CORRUPT")


def test_precycle_state_has_no_cycle_identity(tmp_path) -> None:
    *_, admission = _wo13(tmp_path)
    state, cycle_id = timing_state_before_first_evaluation(admission)
    assert state is Wo15TimingState.TIMING_NOT_EVALUATED
    assert cycle_id is None


def test_completed_5m_and_progression_adapter_use_existing_governed_facts(tmp_path) -> None:
    *_, admission = _wo13(tmp_path)
    session = _session(admission)
    evidence = _evidence(admission, session)
    assert evidence.completion == "COMPLETE" and evidence.timeframe == "5M"
    assert _progression(admission, evidence).semantics is Wo15ProgressionSemantics.ALIGNED
    assert _progression(
        admission, evidence, direction=SemanticDirection.NON_DIRECTIONAL
    ).semantics is Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING
    assert _progression(
        admission, evidence, direction=SemanticDirection.SHORT
    ).semantics is Wo15ProgressionSemantics.CONTRADICTORY
    with pytest.raises(Wo15AdmissionRejected) as rejected:
        bind_completed_five_minute_evidence(
            source=None, market_family=admission.market_family,
            instrument_identity=admission.instrument_identity,
        )
    assert rejected.value.reason is Wo15TrustFailure.FIVE_MINUTE_EVIDENCE_INCOMPLETE


def test_first_cycle_is_strictly_post_plan_and_atomically_links_first_observation(tmp_path) -> None:
    *_, admission = _wo13(tmp_path)
    session = _session(admission)
    stale = _evidence(admission, session, minutes_after=0)
    with pytest.raises(Wo15AdmissionRejected) as rejected:
        create_first_cycle_evaluation(
            admission=admission, session=session, evidence=stale,
            progression=_progression(admission, stale),
            current_state=Wo15TimingState.TIMING_WAITING,
            transition_cause="FIRST_VALID_EVALUATION",
            qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
            cycle_created_at=stale.candle_end + timedelta(seconds=1),
            observed_at=stale.candle_end + timedelta(seconds=2),
        )
    assert rejected.value.reason is Wo15TrustFailure.FIVE_MINUTE_EVIDENCE_STALE
    _, _, evidence, _, evaluation = _evaluation(tmp_path / "valid")
    assert evaluation.cycle.timing_cycle_id == evaluation.observation.timing_cycle_id
    assert evaluation.observation.transition_identity == evaluation.transition.transition_identity


@pytest.mark.parametrize(
    ("change", "reason"),
    (
        ({"canonical_subject_identity": "NSE-EQ-NIFTY"}, Wo15TrustFailure.SUBJECT_MISMATCH),
        ({"instrument_identity": "FOREIGN-INSTRUMENT"}, Wo15TrustFailure.INSTRUMENT_MISMATCH),
        ({"session_identity": "FOREIGN-SESSION"}, Wo15TrustFailure.SESSION_MISMATCH),
    ),
)
def test_subject_instrument_and_session_locality_fail_unavailable(
    tmp_path, change, reason
) -> None:  # type: ignore[no-untyped-def]
    *_, admission = _wo13(tmp_path)
    session = _session(admission)
    evidence = _evidence(admission, session)
    values = asdict(evidence)
    values.update(change)
    values.pop("evidence_identity")
    values.pop("evidence_integrity")
    from kronos.intraday.wo15 import Wo15FiveMinuteEvidence, _identity
    changed = Wo15FiveMinuteEvidence(
        evidence_identity=_identity("INTRADAY-WO15-5M-EVIDENCE-", values),
        evidence_integrity=_identity("INTEGRITY-INTRADAY-WO15-5M-EVIDENCE-", values),
        **values,
    )
    with pytest.raises(Wo15AdmissionRejected) as rejected:
        create_first_cycle_evaluation(
            admission=admission, session=session, evidence=changed,
            progression=_progression(admission, changed),
            current_state=Wo15TimingState.TIMING_WAITING,
            transition_cause="LOCALITY_TEST",
            qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
            cycle_created_at=changed.candle_end + timedelta(seconds=1),
            observed_at=changed.candle_end + timedelta(seconds=2),
        )
    assert rejected.value.reason is reason
    assert rejected.value.timing_state is Wo15TimingState.TIMING_UNAVAILABLE


def test_one_active_cycle_and_successor_after_failed_only(tmp_path) -> None:
    admission, session, _, _, first = _evaluation(
        tmp_path, state=Wo15TimingState.TIMING_FAILED
    )
    later = _evidence(admission, session, minutes_after=10)
    successor = create_successor_cycle_evaluation(
        admission=admission, session=session, predecessor=first,
        reset_evidence_identity="FUTURE-WO15B-RESET-EVIDENCE",
        evidence=later, progression=_progression(admission, later),
        current_state=Wo15TimingState.TIMING_WAITING,
        transition_cause="SUCCESSOR_FOUNDATION_ONLY",
        qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
        cycle_created_at=later.candle_end + timedelta(seconds=1),
        observed_at=later.candle_end + timedelta(seconds=2),
    )
    assert successor.cycle.cycle_ordinal == 2
    assert successor.cycle.predecessor_cycle_identity == first.cycle.timing_cycle_id
    validate_one_active_cycle((
        (first.cycle, Wo15TimingState.TIMING_FAILED),
        (successor.cycle, Wo15TimingState.TIMING_WAITING),
    ))
    with pytest.raises(Wo15ContractError, match="WO15_MULTIPLE_ACTIVE_CYCLES"):
        validate_one_active_cycle((
            (first.cycle, Wo15TimingState.TIMING_WAITING),
            (successor.cycle, Wo15TimingState.TIMING_QUALIFIED),
        ))


def test_mcx_requires_exact_active_contract_roll_and_rejects_reference_market(tmp_path) -> None:
    *_, admission = _mcx_wo13(tmp_path)
    session = _session(admission)
    evidence = _evidence(admission, session)
    evaluation = create_first_cycle_evaluation(
        admission=admission, session=session, evidence=evidence,
        progression=_progression(admission, evidence),
        current_state=Wo15TimingState.TIMING_WAITING,
        transition_cause="MCX_LOCALITY",
        qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
        cycle_created_at=evidence.candle_end + timedelta(seconds=1),
        observed_at=evidence.candle_end + timedelta(seconds=2),
    )
    assert evaluation.cycle.actual_contract_identity == admission.actual_contract_identity
    assert evaluation.cycle.roll_lineage_identity == admission.roll_lineage_identity
    foreign = _evidence(
        admission, session,
        actual_contract_identity="FOREIGN-MCX-CONTRACT",
    )
    with pytest.raises(Wo15AdmissionRejected) as rejected:
        create_first_cycle_evaluation(
            admission=admission, session=session, evidence=foreign,
            progression=_progression(admission, foreign),
            current_state=Wo15TimingState.TIMING_WAITING,
            transition_cause="MCX_LOCALITY",
            qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
            cycle_created_at=foreign.candle_end + timedelta(seconds=1),
            observed_at=foreign.candle_end + timedelta(seconds=2),
        )
    assert rejected.value.reason is Wo15TrustFailure.ACTIVE_CONTRACT_MISMATCH
    assert rejected.value.timing_state is Wo15TimingState.TIMING_UNAVAILABLE

    source = create_governed_historical_candle_payload(
        canonical_subject_identity=admission.canonical_subject_identity,
        exchange="COMEX", market_identity="COMEX",
        market_session_identity=session.session_identity,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        candle_start=admission.analysis_boundary,
        candle_end=admission.analysis_boundary + timedelta(minutes=5),
        open=Decimal("99"), high=Decimal("101"), low=Decimal("98"),
        close=Decimal("100"), volume=100,
        observation_boundary=admission.analysis_boundary + timedelta(minutes=5),
        provider_source_identity="REFERENCE-MARKET",
        source_operation_identity="WO15A-REFERENCE-NON-AUTHORITY",
        provenance=("WO-15A",),
    )
    with pytest.raises(Wo15AdmissionRejected):
        bind_completed_five_minute_evidence(
            source=source, market_family=admission.market_family,
            instrument_identity=admission.instrument_identity,
            actual_contract_identity=admission.actual_contract_identity,
            roll_lineage_identity=admission.roll_lineage_identity,
        )


def test_index_uses_underlying_instrument_and_rejects_option_premium(tmp_path) -> None:
    *_, equity = _wo13(tmp_path)
    values = asdict(equity)
    values.pop("handoff_identity")
    values.pop("handoff_integrity")
    values.update({
        "canonical_subject_identity": "NSE-INDEX-NIFTY",
        "market_family": type(equity.market_family).NSE_INDEX,
        "instrument_identity": "INSTRUMENT:NSE:NIFTY",
        "policy": equity.policy,
    })
    from kronos.intraday.wo15 import _identity
    index = Wo15Wo13Handoff(
        handoff_identity=_identity("INTRADAY-WO15-WO13-HANDOFF-", values),
        handoff_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-WO13-HANDOFF-", values
        ),
        **values,
    )
    session = _session(index)
    underlying = _evidence(index, session)
    accepted = create_first_cycle_evaluation(
        admission=index, session=session, evidence=underlying,
        progression=_progression(index, underlying),
        current_state=Wo15TimingState.TIMING_WAITING,
        transition_cause="INDEX_UNDERLYING_LOCALITY",
        qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
        cycle_created_at=underlying.candle_end + timedelta(seconds=1),
        observed_at=underlying.candle_end + timedelta(seconds=2),
    )
    assert accepted.cycle.instrument_identity == "INSTRUMENT:NSE:NIFTY"
    option = _evidence(index, session, instrument_identity="INSTRUMENT:NFO:NIFTY:CALL")
    with pytest.raises(Wo15AdmissionRejected) as rejected:
        create_first_cycle_evaluation(
            admission=index, session=session, evidence=option,
            progression=_progression(index, option),
            current_state=Wo15TimingState.TIMING_WAITING,
            transition_cause="OPTION_PREMIUM_PROHIBITED",
            qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
            cycle_created_at=option.candle_end + timedelta(seconds=1),
            observed_at=option.candle_end + timedelta(seconds=2),
        )
    assert rejected.value.reason is Wo15TrustFailure.INSTRUMENT_MISMATCH


def test_natural_gas_held_cannot_manufacture_wo15_admission() -> None:
    with pytest.raises(Wo15AdmissionRejected) as rejected:
        create_wo15_wo13_handoff(
            current_pointer=None, trade_plan=None, source_handoff=None
        )
    assert rejected.value.reason is Wo15TrustFailure.WO13_PLAN_NOT_CURRENT


def test_failed_expired_and_qualified_history_are_immutable(tmp_path) -> None:
    admission, session, _, _, waiting = _evaluation(tmp_path)
    later = _evidence(admission, session, minutes_after=10)
    qualified, qualified_transition = create_followup_observation(
        cycle=waiting.cycle, prior_state=Wo15TimingState.TIMING_WAITING,
        current_state=Wo15TimingState.TIMING_QUALIFIED, evidence=later,
        progression=_progression(admission, later),
        transition_cause="VOCABULARY_ONLY",
        qualification_path=Wo15QualificationPath.PULLBACK_CONTINUATION,
        observed_at=later.candle_end + timedelta(seconds=1),
    )
    later_two = _evidence(admission, session, minutes_after=15)
    failed, _ = create_followup_observation(
        cycle=waiting.cycle, prior_state=Wo15TimingState.TIMING_QUALIFIED,
        current_state=Wo15TimingState.TIMING_FAILED, evidence=later_two,
        progression=_progression(admission, later_two),
        transition_cause="VOCABULARY_ONLY",
        qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
        observed_at=later_two.candle_end + timedelta(seconds=1),
    )
    assert qualified.current_state is Wo15TimingState.TIMING_QUALIFIED
    assert qualified_transition.current_state is Wo15TimingState.TIMING_QUALIFIED
    assert failed.current_state is Wo15TimingState.TIMING_FAILED
    with pytest.raises(Wo15ContractError, match="WO15_TIMING_TRANSITION_INVALID"):
        create_followup_observation(
            cycle=waiting.cycle, prior_state=Wo15TimingState.TIMING_FAILED,
            current_state=Wo15TimingState.TIMING_WAITING, evidence=later_two,
            progression=_progression(admission, later_two),
            transition_cause="INVALID", qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
            observed_at=later_two.candle_end + timedelta(seconds=1),
        )
    with pytest.raises(Wo15ContractError, match="WO15_TIMING_TRANSITION_INVALID"):
        create_followup_observation(
            cycle=waiting.cycle, prior_state=Wo15TimingState.TIMING_EXPIRED,
            current_state=Wo15TimingState.TIMING_QUALIFIED, evidence=later_two,
            progression=_progression(admission, later_two),
            transition_cause="INVALID", qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
            observed_at=later_two.candle_end + timedelta(seconds=1),
        )


def test_identity_determinism_material_changes_and_integrity_corruption(tmp_path) -> None:
    admission, session, evidence, progression, evaluation = _evaluation(tmp_path)
    same = create_first_cycle_evaluation(
        admission=admission, session=session, evidence=evidence,
        progression=progression, current_state=Wo15TimingState.TIMING_WAITING,
        transition_cause="SLICE_A_CONTRACT_FIXTURE",
        qualification_path=Wo15QualificationPath.NOT_APPLICABLE,
        cycle_created_at=evidence.candle_end + timedelta(seconds=1),
        observed_at=evidence.candle_end + timedelta(seconds=2),
    )
    assert same == evaluation
    changed = _evidence(admission, session, minutes_after=10)
    assert changed.evidence_identity != evidence.evidence_identity
    with pytest.raises(Wo15ContractError, match="WO15_TIMING_CYCLE_INVALID"):
        replace(evaluation.cycle, timing_cycle_integrity="CORRUPT")
    with pytest.raises(Wo15ContractError, match="WO15_TIMING_OBSERVATION_INVALID"):
        replace(evaluation.observation, observation_integrity="CORRUPT")
    with pytest.raises(Wo15ContractError, match="WO15_TIMING_TRANSITION_INVALID"):
        replace(evaluation.transition, transition_integrity="CORRUPT")


def test_slice_a_has_no_algorithm_telemetry_persistence_runtime_or_authority() -> None:
    source = Path("src/kronos/intraday/wo15.py").read_text(encoding="utf-8")
    prohibited_symbols = (
        "class Wo15Store", "class IntradayWo15Application", "def calculate_atr",
        "def evaluate_pullback",
        "def evaluate_breakout",
        "def place_" + "order",
        "provider_instrument_token", "FastAPI", "HTTPServer",
    )
    assert not any(item in source for item in prohibited_symbols)
    assert "RISK_APPROVED" not in source
    assert "RISK_REJECTED" not in source
    assert "RISK_PERMISSION" not in source
