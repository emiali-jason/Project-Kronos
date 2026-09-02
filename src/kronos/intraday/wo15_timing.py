"""WO-15B deterministic completed-5M Entry-Timing grammar.

This module evaluates only already-governed, completed 5M evidence against an
exact WO-15A admission and immutable WO-13 geometry.  It acquires no data,
calculates no telemetry, persists no state, and owns no Risk, Sponsor,
execution, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping

from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    SemanticDirection,
)
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo15 import (
    WO15_AUTHORITY,
    WO15_CONTRACT_VERSION,
    WO15_POLICY_CHECKSUM,
    WO15_POLICY_IDENTITY,
    WO15_POLICY_VERSION,
    Wo15ContractError,
    Wo15CycleEvaluation,
    Wo15ExpiryCause,
    Wo15FiveMinuteEvidence,
    Wo15PolicyBinding,
    Wo15ProgressionEvidence,
    Wo15ProgressionSemantics,
    Wo15QualificationPath,
    Wo15SessionBinding,
    Wo15TimingState,
    Wo15TrustFailure,
    Wo15Wo13Handoff,
    bind_cycle_evaluation,
    create_first_cycle_evaluation,
    create_followup_observation,
    create_successor_cycle_evaluation,
)


WO15_TIMING_EVALUATOR_IDENTITY = "KRONOS-INTRADAY-WO15-TIMING-EVALUATOR-V1"
WO15_TIMING_RESULT_IDENTITY = (
    "KRONOS-INTRADAY-WO15-TIMING-EVALUATION-RESULT-V1"
)
WO15_TIMING_HISTORY_IDENTITY = "KRONOS-INTRADAY-WO15-TIMING-LOCAL-HISTORY-V1"
WO15_EXPIRY_EVENT_IDENTITY = "KRONOS-INTRADAY-WO15-EXPIRY-EVENT-V1"
WO15_RESET_ASSESSMENT_IDENTITY = "KRONOS-INTRADAY-WO15-RESET-ASSESSMENT-V1"
WO15_TIMING_GRAMMAR_VERSION = WO15_CONTRACT_VERSION


class Wo15TimingGrammarError(Wo15ContractError):
    """Sanitized Slice-B contract or lifecycle error."""


class Wo15TimingCause(StrEnum):
    WAITING_FOR_QUALIFICATION = "WAITING_FOR_QUALIFICATION"
    PULLBACK_CONTINUATION_QUALIFIED = "PULLBACK_CONTINUATION_QUALIFIED"
    PULLBACK_OPPOSING_PROGRESSION = "PULLBACK_OPPOSING_PROGRESSION"
    BREAKOUT_DIRECT_ACCEPTANCE = "BREAKOUT_DIRECT_ACCEPTANCE"
    BREAKOUT_RETEST_RECORDED = "BREAKOUT_RETEST_RECORDED"
    BREAKOUT_RETEST_RESUMPTION = "BREAKOUT_RETEST_RESUMPTION"
    BREAKOUT_RETURNED_INSIDE_RANGE = "BREAKOUT_RETURNED_INSIDE_RANGE"
    QUALIFIED_STATE_PRESERVED = "QUALIFIED_STATE_PRESERVED"
    TRUST_EVIDENCE_UNAVAILABLE = "TRUST_EVIDENCE_UNAVAILABLE"
    SESSION_END = "SESSION_END"
    EXPLICIT_EXPIRY = "EXPLICIT_EXPIRY"


class Wo15ResetDisposition(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    PRIOR_CYCLE_NOT_FAILED = "PRIOR_CYCLE_NOT_FAILED"
    BOUNDARY_NOT_LATER = "BOUNDARY_NOT_LATER"
    TRUST_UNAVAILABLE = "TRUST_UNAVAILABLE"
    SESSION_OR_LINEAGE_EXPIRED = "SESSION_OR_LINEAGE_EXPIRED"
    PROGRESSION_CONTRADICTORY = "PROGRESSION_CONTRADICTORY"
    PROGRESSION_UNAVAILABLE = "PROGRESSION_UNAVAILABLE"
    PRIOR_FAILURE_STILL_HOLDS = "PRIOR_FAILURE_STILL_HOLDS"


@dataclass(frozen=True, slots=True)
class Wo15ExpiryEvent:
    event_identity: str
    event_integrity: str
    cause: Wo15ExpiryCause
    event_boundary: datetime
    source_identity: str
    source_integrity: str
    wo13_trade_plan_identity: str
    session_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    schema_identity: str = WO15_EXPIRY_EVENT_IDENTITY
    schema_version: str = WO15_TIMING_GRAMMAR_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "event_identity", "event_integrity")
        if (
            type(self.cause) is not Wo15ExpiryCause
            or not _aware(self.event_boundary)
            or not _texts((
                self.source_identity,
                self.source_integrity,
                self.wo13_trade_plan_identity,
                self.session_identity,
                self.instrument_identity,
            ))
            or not _optional_text(self.actual_contract_identity)
            or not _optional_text(self.roll_lineage_identity)
            or self.schema_identity != WO15_EXPIRY_EVENT_IDENTITY
            or self.schema_version != WO15_TIMING_GRAMMAR_VERSION
            or self.event_identity != _identity("INTRADAY-WO15-EXPIRY-", values)
            or self.event_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-EXPIRY-", values)
        ):
            raise Wo15TimingGrammarError("WO15_EXPIRY_EVENT_INVALID")


def create_wo15_expiry_event(
    *,
    cause: Wo15ExpiryCause,
    event_boundary: datetime,
    source_identity: str,
    source_integrity: str,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
) -> Wo15ExpiryEvent:
    values = {
        "cause": cause,
        "event_boundary": event_boundary,
        "source_identity": source_identity,
        "source_integrity": source_integrity,
        "wo13_trade_plan_identity": admission.wo13_trade_plan_identity,
        "session_identity": session.session_identity,
        "instrument_identity": admission.instrument_identity,
        "actual_contract_identity": admission.actual_contract_identity,
        "roll_lineage_identity": admission.roll_lineage_identity,
        "schema_identity": WO15_EXPIRY_EVENT_IDENTITY,
        "schema_version": WO15_TIMING_GRAMMAR_VERSION,
    }
    return Wo15ExpiryEvent(
        event_identity=_identity("INTRADAY-WO15-EXPIRY-", values),
        event_integrity=_identity("INTEGRITY-INTRADAY-WO15-EXPIRY-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo15TimingLocalHistory:
    history_identity: str
    history_integrity: str
    timing_cycle_id: str
    latest_state: Wo15TimingState
    latest_evidence_boundary: datetime
    first_entry_interaction_evidence_identity: str | None
    first_entry_interaction_evidence_integrity: str | None
    first_entry_interaction_boundary: datetime | None
    first_entry_interaction_at: datetime | None
    first_acceptance_evidence_identity: str | None
    first_acceptance_evidence_integrity: str | None
    first_acceptance_boundary: datetime | None
    retest_evidence_identity: str | None
    retest_evidence_integrity: str | None
    retest_boundary: datetime | None
    retest_high: Decimal | None
    retest_low: Decimal | None
    first_qualification_boundary: datetime | None
    first_qualification_at: datetime | None
    failure_evidence_identity: str | None
    failure_evidence_integrity: str | None
    failure_boundary: datetime | None
    failure_at: datetime | None
    expiry_cause: Wo15ExpiryCause | None
    expiry_boundary: datetime | None
    expiry_at: datetime | None
    schema_identity: str = WO15_TIMING_HISTORY_IDENTITY
    schema_version: str = WO15_TIMING_GRAMMAR_VERSION

    def __post_init__(self) -> None:
        for name in ("retest_high", "retest_low"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(value))
        values = _without(self, "history_identity", "history_integrity")
        interaction = (
            self.first_entry_interaction_evidence_identity,
            self.first_entry_interaction_evidence_integrity,
            self.first_entry_interaction_boundary,
            self.first_entry_interaction_at,
        )
        acceptance = (
            self.first_acceptance_evidence_identity,
            self.first_acceptance_evidence_integrity,
            self.first_acceptance_boundary,
        )
        retest = (
            self.retest_evidence_identity,
            self.retest_evidence_integrity,
            self.retest_boundary,
            self.retest_high,
            self.retest_low,
        )
        qualification = (
            self.first_qualification_boundary,
            self.first_qualification_at,
        )
        failure = (
            self.failure_evidence_identity,
            self.failure_evidence_integrity,
            self.failure_boundary,
            self.failure_at,
        )
        expiry = (self.expiry_cause, self.expiry_boundary, self.expiry_at)
        if (
            not _text(self.timing_cycle_id)
            or type(self.latest_state) is not Wo15TimingState
            or not _aware(self.latest_evidence_boundary)
            or not _all_or_none(interaction, text=2, aware=2)
            or not _all_or_none(acceptance, text=2, aware=1)
            or not _all_or_none(retest, text=2, aware=1, decimal=2)
            or not _all_or_none(qualification, aware=2)
            or not _all_or_none(failure, text=2, aware=2)
            or not _all_or_none(expiry, enum=Wo15ExpiryCause, aware=2)
            or self.schema_identity != WO15_TIMING_HISTORY_IDENTITY
            or self.schema_version != WO15_TIMING_GRAMMAR_VERSION
            or self.history_identity != _identity("INTRADAY-WO15-HISTORY-", values)
            or self.history_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-HISTORY-", values)
        ):
            raise Wo15TimingGrammarError("WO15_TIMING_HISTORY_INVALID")


@dataclass(frozen=True, slots=True)
class Wo15TimingEvaluationResult:
    result_identity: str
    result_integrity: str
    timing_cycle_id: str | None
    wo13_trade_plan_identity: str
    prior_result_identity: str | None
    prior_state: Wo15TimingState
    current_state: Wo15TimingState
    cause: Wo15TimingCause
    qualification_path: Wo15QualificationPath
    evidence_identity: str | None
    evidence_integrity: str | None
    observation_boundary: datetime
    progression_identity: str | None
    progression_integrity: str | None
    progression_semantics: Wo15ProgressionSemantics | None
    expiry_cause: Wo15ExpiryCause | None
    trust_failure: Wo15TrustFailure | None
    transition_created: bool
    cycle_evaluation: Wo15CycleEvaluation | None
    local_history: Wo15TimingLocalHistory | None
    policy: Wo15PolicyBinding
    schema_identity: str = WO15_TIMING_RESULT_IDENTITY
    schema_version: str = WO15_TIMING_GRAMMAR_VERSION
    evaluator_identity: str = WO15_TIMING_EVALUATOR_IDENTITY
    authority: str = WO15_AUTHORITY
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "result_identity", "result_integrity")
        evidence = (self.evidence_identity, self.evidence_integrity)
        progression = (
            self.progression_identity,
            self.progression_integrity,
            self.progression_semantics,
        )
        if (
            not _text(self.wo13_trade_plan_identity)
            or not _optional_text(self.timing_cycle_id)
            or not _optional_text(self.prior_result_identity)
            or type(self.prior_state) is not Wo15TimingState
            or type(self.current_state) is not Wo15TimingState
            or type(self.cause) is not Wo15TimingCause
            or type(self.qualification_path) is not Wo15QualificationPath
            or not _aware(self.observation_boundary)
            or not _all_or_none(evidence, text=2)
            or not _all_or_none(
                progression, text=2, enum=Wo15ProgressionSemantics
            )
            or (self.current_state is Wo15TimingState.TIMING_EXPIRED)
            != (self.expiry_cause is not None)
            or (self.current_state is Wo15TimingState.TIMING_UNAVAILABLE)
            != (self.trust_failure is not None)
            or type(self.transition_created) is not bool
            or type(self.policy) is not Wo15PolicyBinding
            or self.schema_identity != WO15_TIMING_RESULT_IDENTITY
            or self.schema_version != WO15_TIMING_GRAMMAR_VERSION
            or self.evaluator_identity != WO15_TIMING_EVALUATOR_IDENTITY
            or self.authority != WO15_AUTHORITY
            or any((
                self.sponsor_decision_authority,
                self.execution_authority,
                self.broker_authority,
            ))
            or self.result_identity != _identity("INTRADAY-WO15-RESULT-", values)
            or self.result_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-RESULT-", values)
        ):
            raise Wo15TimingGrammarError("WO15_TIMING_RESULT_INVALID")
        if self.cycle_evaluation is None:
            if self.transition_created or self.timing_cycle_id is not None:
                raise Wo15TimingGrammarError("WO15_TIMING_RESULT_INVALID")
        else:
            if (
                type(self.cycle_evaluation) is not Wo15CycleEvaluation
                or self.timing_cycle_id
                != self.cycle_evaluation.cycle.timing_cycle_id
                or self.local_history is None
                or self.local_history.timing_cycle_id != self.timing_cycle_id
                or self.local_history.latest_state is not self.current_state
            ):
                raise Wo15TimingGrammarError("WO15_TIMING_RESULT_INVALID")


@dataclass(frozen=True, slots=True)
class Wo15ResetAssessment:
    assessment_identity: str
    assessment_integrity: str
    eligible: bool
    disposition: Wo15ResetDisposition
    predecessor_result_identity: str
    predecessor_cycle_identity: str
    predecessor_failure_transition_identity: str
    predecessor_failure_evidence_identity: str
    candidate_evidence_identity: str
    candidate_evidence_integrity: str
    candidate_boundary: datetime
    progression_identity: str
    progression_integrity: str
    progression_semantics: Wo15ProgressionSemantics
    initial_state: Wo15TimingState | None
    qualification_path: Wo15QualificationPath
    policy: Wo15PolicyBinding
    schema_identity: str = WO15_RESET_ASSESSMENT_IDENTITY
    schema_version: str = WO15_TIMING_GRAMMAR_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "assessment_identity", "assessment_integrity")
        if (
            type(self.eligible) is not bool
            or type(self.disposition) is not Wo15ResetDisposition
            or not _texts((
                self.predecessor_result_identity,
                self.predecessor_cycle_identity,
                self.predecessor_failure_transition_identity,
                self.predecessor_failure_evidence_identity,
                self.candidate_evidence_identity,
                self.candidate_evidence_integrity,
                self.progression_identity,
                self.progression_integrity,
            ))
            or not _aware(self.candidate_boundary)
            or type(self.progression_semantics) is not Wo15ProgressionSemantics
            or type(self.qualification_path) is not Wo15QualificationPath
            or type(self.policy) is not Wo15PolicyBinding
            or self.eligible != (self.disposition is Wo15ResetDisposition.ELIGIBLE)
            or self.eligible
            != (self.initial_state in {
                Wo15TimingState.TIMING_WAITING,
                Wo15TimingState.TIMING_QUALIFIED,
            })
            or self.schema_identity != WO15_RESET_ASSESSMENT_IDENTITY
            or self.schema_version != WO15_TIMING_GRAMMAR_VERSION
            or self.assessment_identity
            != _identity("INTRADAY-WO15-RESET-", values)
            or self.assessment_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-RESET-", values)
        ):
            raise Wo15TimingGrammarError("WO15_RESET_ASSESSMENT_INVALID")


def evaluate_wo15_timing(
    *,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    source_candle: GovernedHistoricalCandlePayload | None,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
    observed_at: datetime,
    previous: Wo15TimingEvaluationResult | None = None,
    expiry_event: Wo15ExpiryEvent | None = None,
    wo14_reference_state: str | None = None,
    model_rr_context: Decimal | None = None,
) -> Wo15TimingEvaluationResult:
    """Apply exact Slice-B precedence and immutable setup grammar."""

    del wo14_reference_state, model_rr_context  # explicit non-authorities
    if not _aware(observed_at):
        raise Wo15TimingGrammarError("WO15_OBSERVED_AT_INVALID")
    _require_nonterminal(previous)
    trust_failure = _trust_failure(
        admission=admission,
        session=session,
        source=source_candle,
        evidence=evidence,
        progression=progression,
        previous=previous,
        observed_at=observed_at,
        expiry_event=expiry_event,
    )
    prior_state = (
        Wo15TimingState.TIMING_NOT_EVALUATED
        if previous is None
        else previous.current_state
    )
    if trust_failure is not None:
        return _result(
            admission=admission,
            evidence=evidence,
            progression=progression,
            previous=previous,
            prior_state=prior_state,
            state=Wo15TimingState.TIMING_UNAVAILABLE,
            cause=Wo15TimingCause.TRUST_EVIDENCE_UNAVAILABLE,
            path=Wo15QualificationPath.NOT_APPLICABLE,
            expiry_cause=None,
            trust_failure=trust_failure,
            cycle_evaluation=None,
            local_history=None,
            transition_created=False,
        )
    assert source_candle is not None

    expiry_cause, expiry_boundary = _expiry(
        admission, session, evidence, observed_at, expiry_event
    )
    facts = _timing_facts(admission, source_candle, previous)
    if progression.semantics is Wo15ProgressionSemantics.UNAVAILABLE:
        expiry_cause = None
        expiry_boundary = None
        state = Wo15TimingState.TIMING_UNAVAILABLE
        cause = Wo15TimingCause.TRUST_EVIDENCE_UNAVAILABLE
        path = Wo15QualificationPath.NOT_APPLICABLE
    elif expiry_cause is not None:
        state = Wo15TimingState.TIMING_EXPIRED
        cause = (
            Wo15TimingCause.SESSION_END
            if expiry_cause is Wo15ExpiryCause.SESSION_END
            else Wo15TimingCause.EXPLICIT_EXPIRY
        )
        path = Wo15QualificationPath.NOT_APPLICABLE
    else:
        state, cause, path = _grammar(admission, source_candle, progression, previous, facts)
    decision_trust_failure = (
        Wo15TrustFailure.UPSTREAM_COMMISSIONING_UNAVAILABLE
        if state is Wo15TimingState.TIMING_UNAVAILABLE
        else None
    )

    if (
        previous is not None
        and previous.current_state is Wo15TimingState.TIMING_QUALIFIED
        and state is Wo15TimingState.TIMING_UNAVAILABLE
    ):
        return _result(
            admission=admission,
            evidence=evidence,
            progression=progression,
            previous=previous,
            prior_state=prior_state,
            state=state,
            cause=cause,
            path=path,
            expiry_cause=None,
            trust_failure=decision_trust_failure,
            cycle_evaluation=None,
            local_history=None,
            transition_created=False,
        )

    if previous is not None and previous.current_state is Wo15TimingState.TIMING_QUALIFIED:
        if state not in {
            Wo15TimingState.TIMING_FAILED,
            Wo15TimingState.TIMING_EXPIRED,
        }:
            state = Wo15TimingState.TIMING_QUALIFIED
            cause = Wo15TimingCause.QUALIFIED_STATE_PRESERVED
            path = previous.qualification_path
            evaluation = previous.cycle_evaluation
            transition_created = False
        else:
            evaluation = _slice_a_evaluation(
                admission=admission,
                session=session,
                evidence=evidence,
                progression=progression,
                previous=previous,
                state=state,
                cause=cause,
                path=path,
                observed_at=observed_at,
                expiry_cause=expiry_cause,
                trust_failure=decision_trust_failure,
            )
            transition_created = True
    else:
        evaluation = _slice_a_evaluation(
            admission=admission,
            session=session,
            evidence=evidence,
            progression=progression,
            previous=previous,
            state=state,
            cause=cause,
            path=path,
            observed_at=observed_at,
            expiry_cause=expiry_cause,
            trust_failure=decision_trust_failure,
        )
        transition_created = evaluation is not None

    history = None
    if evaluation is not None:
        history = _history(
            cycle_id=evaluation.cycle.timing_cycle_id,
            previous=previous.local_history if previous is not None else None,
            state=state,
            evidence=evidence,
            source=source_candle,
            facts=facts,
            observed_at=observed_at,
            expiry_cause=expiry_cause,
            expiry_boundary=expiry_boundary,
        )
    return _result(
        admission=admission,
        evidence=evidence,
        progression=progression,
        previous=previous,
        prior_state=prior_state,
        state=state,
        cause=cause,
        path=path,
        expiry_cause=expiry_cause,
        trust_failure=decision_trust_failure,
        cycle_evaluation=evaluation,
        local_history=history,
        transition_created=transition_created,
    )


def evaluate_wo15_successor_cycle(
    *,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    predecessor: Wo15TimingEvaluationResult,
    source_candle: GovernedHistoricalCandlePayload | None,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
    observed_at: datetime,
    expiry_event: Wo15ExpiryEvent | None = None,
) -> tuple[Wo15ResetAssessment, Wo15TimingEvaluationResult | None]:
    """Assess and, only when eligible, atomically create a successor cycle."""

    disposition = Wo15ResetDisposition.ELIGIBLE
    trust = _trust_failure(
        admission=admission,
        session=session,
        source=source_candle,
        evidence=evidence,
        progression=progression,
        previous=None,
        observed_at=observed_at,
        expiry_event=expiry_event,
    )
    if (
        type(predecessor) is not Wo15TimingEvaluationResult
        or predecessor.current_state is not Wo15TimingState.TIMING_FAILED
        or predecessor.cycle_evaluation is None
        or predecessor.local_history is None
    ):
        disposition = Wo15ResetDisposition.PRIOR_CYCLE_NOT_FAILED
    elif trust is not None:
        disposition = Wo15ResetDisposition.TRUST_UNAVAILABLE
    elif evidence.candle_end <= predecessor.observation_boundary:
        disposition = Wo15ResetDisposition.BOUNDARY_NOT_LATER
    elif (
        predecessor.wo13_trade_plan_identity != admission.wo13_trade_plan_identity
        or predecessor.cycle_evaluation.cycle.session_identity != session.session_identity
        or predecessor.cycle_evaluation.cycle.instrument_identity
        != admission.instrument_identity
        or predecessor.cycle_evaluation.cycle.actual_contract_identity
        != admission.actual_contract_identity
        or predecessor.cycle_evaluation.cycle.roll_lineage_identity
        != admission.roll_lineage_identity
        or predecessor.cycle_evaluation.cycle.direction is not admission.direction
        or predecessor.cycle_evaluation.cycle.setup_family is not admission.setup_family
    ):
        disposition = Wo15ResetDisposition.TRUST_UNAVAILABLE
    elif _expiry(admission, session, evidence, observed_at, expiry_event)[0] is not None:
        disposition = Wo15ResetDisposition.SESSION_OR_LINEAGE_EXPIRED
    elif progression.semantics is Wo15ProgressionSemantics.UNAVAILABLE:
        disposition = Wo15ResetDisposition.PROGRESSION_UNAVAILABLE
    elif progression.semantics is Wo15ProgressionSemantics.CONTRADICTORY:
        disposition = Wo15ResetDisposition.PROGRESSION_CONTRADICTORY
    elif source_candle is None or _reset_failure_still_holds(admission, source_candle):
        disposition = Wo15ResetDisposition.PRIOR_FAILURE_STILL_HOLDS

    eligible = disposition is Wo15ResetDisposition.ELIGIBLE
    state: Wo15TimingState | None = None
    path = Wo15QualificationPath.NOT_APPLICABLE
    if eligible:
        assert source_candle is not None
        qualified, path = _qualification(admission, source_candle, progression, None)
        state = (
            Wo15TimingState.TIMING_QUALIFIED
            if qualified
            else Wo15TimingState.TIMING_WAITING
        )
    assessment = _reset_assessment(
        predecessor=predecessor,
        evidence=evidence,
        progression=progression,
        eligible=eligible,
        disposition=disposition,
        initial_state=state,
        path=path,
    )
    if not eligible:
        return assessment, None

    assert source_candle is not None and state is not None
    evaluation = create_successor_cycle_evaluation(
        admission=admission,
        session=session,
        predecessor=predecessor.cycle_evaluation,
        reset_evidence_identity=assessment.assessment_identity,
        evidence=evidence,
        progression=progression,
        current_state=state,
        transition_cause=(
            Wo15TimingCause.PULLBACK_CONTINUATION_QUALIFIED.value
            if state is Wo15TimingState.TIMING_QUALIFIED
            and admission.setup_family
            is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION
            else Wo15TimingCause.BREAKOUT_DIRECT_ACCEPTANCE.value
            if state is Wo15TimingState.TIMING_QUALIFIED
            else Wo15TimingCause.WAITING_FOR_QUALIFICATION.value
        ),
        qualification_path=path,
        cycle_created_at=observed_at,
        observed_at=observed_at,
        provenance=("ADR-0025", "WO-15B-RESET"),
    )
    facts = _timing_facts(admission, source_candle, None)
    history = _history(
        cycle_id=evaluation.cycle.timing_cycle_id,
        previous=None,
        state=state,
        evidence=evidence,
        source=source_candle,
        facts=facts,
        observed_at=observed_at,
        expiry_cause=None,
        expiry_boundary=None,
    )
    cause = (
        Wo15TimingCause.PULLBACK_CONTINUATION_QUALIFIED
        if state is Wo15TimingState.TIMING_QUALIFIED
        and admission.setup_family
        is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION
        else Wo15TimingCause.BREAKOUT_DIRECT_ACCEPTANCE
        if state is Wo15TimingState.TIMING_QUALIFIED
        else Wo15TimingCause.WAITING_FOR_QUALIFICATION
    )
    result = _result(
        admission=admission,
        evidence=evidence,
        progression=progression,
        previous=None,
        prior_state=Wo15TimingState.TIMING_NOT_EVALUATED,
        state=state,
        cause=cause,
        path=path,
        expiry_cause=None,
        trust_failure=None,
        cycle_evaluation=evaluation,
        local_history=history,
        transition_created=True,
    )
    return assessment, result


@dataclass(frozen=True, slots=True)
class _TimingFacts:
    entry_interaction: bool
    acceptance: bool
    retest: bool
    resumption: bool
    breakout_interaction_previously_active: bool


def _timing_facts(
    admission: Wo15Wo13Handoff,
    source: GovernedHistoricalCandlePayload,
    previous: Wo15TimingEvaluationResult | None,
) -> _TimingFacts:
    entry = admission.entry_reference
    history = previous.local_history if previous is not None else None
    interaction = source.low <= entry <= source.high
    acceptance = _strict_price(admission.direction, source.close, entry)
    prior_acceptance = history is not None and history.first_acceptance_boundary is not None
    retest = False
    if (
        admission.setup_family is Wo13SetupFamily.INTRADAY_RANGE_BREAKOUT
        and prior_acceptance
    ):
        retest = (
            source.low <= entry and source.close >= entry
            if admission.direction is SemanticDirection.LONG
            else source.high >= entry and source.close <= entry
        )
    resumption = False
    if history is not None and history.retest_boundary is not None:
        if admission.direction is SemanticDirection.LONG:
            assert history.retest_high is not None
            resumption = source.close > history.retest_high
        else:
            assert history.retest_low is not None
            resumption = source.close < history.retest_low
    prior_active = history is not None and (
        history.first_entry_interaction_boundary is not None
        or history.first_acceptance_boundary is not None
    )
    return _TimingFacts(interaction, acceptance, retest, resumption, prior_active)


def _grammar(
    admission: Wo15Wo13Handoff,
    source: GovernedHistoricalCandlePayload,
    progression: Wo15ProgressionEvidence,
    previous: Wo15TimingEvaluationResult | None,
    facts: _TimingFacts,
) -> tuple[Wo15TimingState, Wo15TimingCause, Wo15QualificationPath]:
    if progression.semantics is Wo15ProgressionSemantics.UNAVAILABLE:
        return (
            Wo15TimingState.TIMING_UNAVAILABLE,
            Wo15TimingCause.TRUST_EVIDENCE_UNAVAILABLE,
            Wo15QualificationPath.NOT_APPLICABLE,
        )
    if _failure(admission, source, progression, facts):
        cause = (
            Wo15TimingCause.PULLBACK_OPPOSING_PROGRESSION
            if admission.setup_family
            is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION
            else Wo15TimingCause.BREAKOUT_RETURNED_INSIDE_RANGE
        )
        return (
            Wo15TimingState.TIMING_FAILED,
            cause,
            Wo15QualificationPath.NOT_APPLICABLE,
        )
    qualified, path = _qualification(admission, source, progression, previous)
    if qualified:
        cause = (
            Wo15TimingCause.PULLBACK_CONTINUATION_QUALIFIED
            if path is Wo15QualificationPath.PULLBACK_CONTINUATION
            else Wo15TimingCause.BREAKOUT_RETEST_RESUMPTION
            if path is Wo15QualificationPath.RETEST_RESUMPTION
            else Wo15TimingCause.BREAKOUT_DIRECT_ACCEPTANCE
        )
        return Wo15TimingState.TIMING_QUALIFIED, cause, path
    if facts.retest:
        return (
            Wo15TimingState.TIMING_WAITING,
            Wo15TimingCause.BREAKOUT_RETEST_RECORDED,
            Wo15QualificationPath.NOT_APPLICABLE,
        )
    return (
        Wo15TimingState.TIMING_WAITING,
        Wo15TimingCause.WAITING_FOR_QUALIFICATION,
        Wo15QualificationPath.NOT_APPLICABLE,
    )


def _qualification(
    admission: Wo15Wo13Handoff,
    source: GovernedHistoricalCandlePayload,
    progression: Wo15ProgressionEvidence,
    previous: Wo15TimingEvaluationResult | None,
) -> tuple[bool, Wo15QualificationPath]:
    aligned = progression.semantics is Wo15ProgressionSemantics.ALIGNED
    if not aligned:
        return False, Wo15QualificationPath.NOT_APPLICABLE
    if admission.setup_family is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION:
        return (
            _strict_price(admission.direction, source.close, admission.entry_reference),
            Wo15QualificationPath.PULLBACK_CONTINUATION,
        )
    history = previous.local_history if previous is not None else None
    if history is not None and history.retest_boundary is not None:
        resumed = (
            source.close > history.retest_high
            if admission.direction is SemanticDirection.LONG
            else source.close < history.retest_low
        )
        return (
            resumed,
            Wo15QualificationPath.RETEST_RESUMPTION
            if resumed
            else Wo15QualificationPath.NOT_APPLICABLE,
        )
    return (
        _strict_price(admission.direction, source.close, admission.entry_reference),
        Wo15QualificationPath.DIRECT_ACCEPTANCE,
    )


def _failure(
    admission: Wo15Wo13Handoff,
    source: GovernedHistoricalCandlePayload,
    progression: Wo15ProgressionEvidence,
    facts: _TimingFacts,
) -> bool:
    if admission.setup_family is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION:
        return progression.semantics is Wo15ProgressionSemantics.CONTRADICTORY
    if not facts.breakout_interaction_previously_active:
        return False
    return (
        source.close < admission.entry_reference
        if admission.direction is SemanticDirection.LONG
        else source.close > admission.entry_reference
    )


def _reset_failure_still_holds(
    admission: Wo15Wo13Handoff,
    source: GovernedHistoricalCandlePayload,
) -> bool:
    if admission.setup_family is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION:
        return False
    return (
        source.close < admission.entry_reference
        if admission.direction is SemanticDirection.LONG
        else source.close > admission.entry_reference
    )


def _strict_price(direction: SemanticDirection, close: Decimal, entry: Decimal) -> bool:
    return close > entry if direction is SemanticDirection.LONG else close < entry


def _trust_failure(
    *,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    source: GovernedHistoricalCandlePayload | None,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
    previous: Wo15TimingEvaluationResult | None,
    observed_at: datetime,
    expiry_event: Wo15ExpiryEvent | None,
) -> Wo15TrustFailure | None:
    try:
        admission.__post_init__()
        session.__post_init__()
        evidence.__post_init__()
        progression.__post_init__()
        if source is None:
            return Wo15TrustFailure.FIVE_MINUTE_EVIDENCE_INCOMPLETE
        source.__post_init__()
    except (ValueError, TypeError):
        return Wo15TrustFailure.SOURCE_EVIDENCE_INVALID
    if source.completion_state != "COMPLETE" or source.timeframe.value != "5M":
        return Wo15TrustFailure.FIVE_MINUTE_EVIDENCE_INCOMPLETE
    pairs = (
        (evidence.source_candle_identity, source.candle_identity,
         Wo15TrustFailure.SOURCE_EVIDENCE_INVALID),
        (evidence.source_candle_integrity, source.integrity_identity,
         Wo15TrustFailure.SOURCE_EVIDENCE_INVALID),
        (evidence.canonical_subject_identity, admission.canonical_subject_identity,
         Wo15TrustFailure.SUBJECT_MISMATCH),
        (source.canonical_subject_identity, admission.canonical_subject_identity,
         Wo15TrustFailure.SUBJECT_MISMATCH),
        (evidence.market_family, admission.market_family,
         Wo15TrustFailure.MARKET_FAMILY_MISMATCH),
        (evidence.instrument_identity, admission.instrument_identity,
         Wo15TrustFailure.INSTRUMENT_MISMATCH),
        (evidence.actual_contract_identity, admission.actual_contract_identity,
         Wo15TrustFailure.ACTIVE_CONTRACT_MISMATCH),
        (evidence.roll_lineage_identity, admission.roll_lineage_identity,
         Wo15TrustFailure.ROLL_LINEAGE_MISMATCH),
        (evidence.session_identity, session.session_identity,
         Wo15TrustFailure.SESSION_MISMATCH),
        (source.market_session_identity, session.session_identity,
         Wo15TrustFailure.SESSION_MISMATCH),
        (evidence.candle_start, source.candle_start,
         Wo15TrustFailure.OBSERVATION_BOUNDARY_MISMATCH),
        (evidence.candle_end, source.candle_end,
         Wo15TrustFailure.OBSERVATION_BOUNDARY_MISMATCH),
        (evidence.observation_boundary, source.observation_boundary,
         Wo15TrustFailure.OBSERVATION_BOUNDARY_MISMATCH),
        (progression.canonical_subject_identity, admission.canonical_subject_identity,
         Wo15TrustFailure.SUBJECT_MISMATCH),
        (progression.inherited_direction, admission.direction,
         Wo15TrustFailure.DIRECTION_MISMATCH),
        (progression.analysis_boundary, evidence.observation_boundary,
         Wo15TrustFailure.OBSERVATION_BOUNDARY_MISMATCH),
    )
    for actual, expected, failure in pairs:
        if actual != expected:
            return failure
    if evidence.candle_end <= admission.analysis_boundary:
        return Wo15TrustFailure.FIVE_MINUTE_EVIDENCE_STALE
    if evidence.candle_end > observed_at:
        return Wo15TrustFailure.OBSERVATION_BOUNDARY_MISMATCH
    expected_exchange = (
        "MCX" if admission.market_family.value == "MCX" else "NSE"
    )
    if evidence.exchange != expected_exchange or source.exchange != expected_exchange:
        return Wo15TrustFailure.INSTRUMENT_MISMATCH
    if not any(
        opens_at <= evidence.candle_start and evidence.candle_end <= closes_at
        for opens_at, closes_at in session.windows
    ):
        return Wo15TrustFailure.OBSERVATION_BOUNDARY_MISMATCH
    if previous is not None:
        if (
            type(previous) is not Wo15TimingEvaluationResult
            or previous.wo13_trade_plan_identity != admission.wo13_trade_plan_identity
            or previous.cycle_evaluation is None
            or previous.cycle_evaluation.cycle.wo13_trade_plan_integrity
            != admission.wo13_trade_plan_integrity
            or previous.cycle_evaluation.cycle.session_identity
            != session.session_identity
            or evidence.candle_end <= previous.observation_boundary
        ):
            return Wo15TrustFailure.WO13_PLAN_NOT_CURRENT
    if expiry_event is not None:
        try:
            expiry_event.__post_init__()
        except (ValueError, TypeError):
            return Wo15TrustFailure.SOURCE_EVIDENCE_INVALID
        if expiry_event.wo13_trade_plan_identity != admission.wo13_trade_plan_identity:
            return Wo15TrustFailure.WO13_PLAN_NOT_CURRENT
        if expiry_event.session_identity != session.session_identity:
            return Wo15TrustFailure.SESSION_MISMATCH
        if expiry_event.instrument_identity != admission.instrument_identity:
            return Wo15TrustFailure.INSTRUMENT_MISMATCH
        if expiry_event.actual_contract_identity != admission.actual_contract_identity:
            return Wo15TrustFailure.ACTIVE_CONTRACT_MISMATCH
        if expiry_event.roll_lineage_identity != admission.roll_lineage_identity:
            return Wo15TrustFailure.ROLL_LINEAGE_MISMATCH
        if expiry_event.event_boundary > observed_at:
            return Wo15TrustFailure.OBSERVATION_BOUNDARY_MISMATCH
    return None


def _expiry(
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    evidence: Wo15FiveMinuteEvidence,
    observed_at: datetime,
    expiry_event: Wo15ExpiryEvent | None,
) -> tuple[Wo15ExpiryCause | None, datetime | None]:
    del admission, observed_at
    if evidence.candle_end >= session.session_closes_at:
        return Wo15ExpiryCause.SESSION_END, session.session_closes_at
    if expiry_event is not None:
        return expiry_event.cause, expiry_event.event_boundary
    return None, None


def _require_nonterminal(previous: Wo15TimingEvaluationResult | None) -> None:
    if previous is None:
        return
    if previous.current_state in {
        Wo15TimingState.TIMING_FAILED,
        Wo15TimingState.TIMING_EXPIRED,
        Wo15TimingState.TIMING_UNAVAILABLE,
    }:
        raise Wo15TimingGrammarError("WO15_TERMINAL_CYCLE_REEVALUATION_PROHIBITED")


def _slice_a_evaluation(
    *,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
    previous: Wo15TimingEvaluationResult | None,
    state: Wo15TimingState,
    cause: Wo15TimingCause,
    path: Wo15QualificationPath,
    observed_at: datetime,
    expiry_cause: Wo15ExpiryCause | None,
    trust_failure: Wo15TrustFailure | None,
) -> Wo15CycleEvaluation | None:
    if previous is None:
        if state is Wo15TimingState.TIMING_EXPIRED:
            return None
        return create_first_cycle_evaluation(
            admission=admission,
            session=session,
            evidence=evidence,
            progression=progression,
            current_state=state,
            transition_cause=cause.value,
            qualification_path=path,
            cycle_created_at=observed_at,
            observed_at=observed_at,
            expiry_cause=expiry_cause,
            trust_failure=trust_failure,
            provenance=("ADR-0025", "WO-15B"),
        )
    assert previous.cycle_evaluation is not None
    observation, transition = create_followup_observation(
        cycle=previous.cycle_evaluation.cycle,
        prior_state=previous.current_state,
        current_state=state,
        evidence=evidence,
        progression=progression,
        transition_cause=cause.value,
        qualification_path=path,
        observed_at=observed_at,
        expiry_cause=expiry_cause,
        trust_failure=trust_failure,
        provenance=("ADR-0025", "WO-15B"),
    )
    return bind_cycle_evaluation(
        cycle=previous.cycle_evaluation.cycle,
        observation=observation,
        transition=transition,
    )


def _history(
    *,
    cycle_id: str,
    previous: Wo15TimingLocalHistory | None,
    state: Wo15TimingState,
    evidence: Wo15FiveMinuteEvidence,
    source: GovernedHistoricalCandlePayload,
    facts: _TimingFacts,
    observed_at: datetime,
    expiry_cause: Wo15ExpiryCause | None,
    expiry_boundary: datetime | None,
) -> Wo15TimingLocalHistory:
    def retained(name: str) -> object:
        return getattr(previous, name) if previous is not None else None

    interaction_new = previous is None or retained(
        "first_entry_interaction_boundary"
    ) is None
    acceptance_new = previous is None or retained("first_acceptance_boundary") is None
    retest_new = previous is None or retained("retest_boundary") is None
    qualification_new = previous is None or retained(
        "first_qualification_boundary"
    ) is None
    values = {
        "timing_cycle_id": cycle_id,
        "latest_state": state,
        "latest_evidence_boundary": evidence.candle_end,
        "first_entry_interaction_evidence_identity": (
            evidence.evidence_identity
            if facts.entry_interaction and interaction_new
            else retained("first_entry_interaction_evidence_identity")
        ),
        "first_entry_interaction_evidence_integrity": (
            evidence.evidence_integrity
            if facts.entry_interaction and interaction_new
            else retained("first_entry_interaction_evidence_integrity")
        ),
        "first_entry_interaction_boundary": (
            evidence.candle_end
            if facts.entry_interaction and interaction_new
            else retained("first_entry_interaction_boundary")
        ),
        "first_entry_interaction_at": (
            observed_at
            if facts.entry_interaction and interaction_new
            else retained("first_entry_interaction_at")
        ),
        "first_acceptance_evidence_identity": (
            evidence.evidence_identity
            if facts.acceptance and acceptance_new
            else retained("first_acceptance_evidence_identity")
        ),
        "first_acceptance_evidence_integrity": (
            evidence.evidence_integrity
            if facts.acceptance and acceptance_new
            else retained("first_acceptance_evidence_integrity")
        ),
        "first_acceptance_boundary": (
            evidence.candle_end
            if facts.acceptance and acceptance_new
            else retained("first_acceptance_boundary")
        ),
        "retest_evidence_identity": (
            evidence.evidence_identity
            if facts.retest and retest_new
            else retained("retest_evidence_identity")
        ),
        "retest_evidence_integrity": (
            evidence.evidence_integrity
            if facts.retest and retest_new
            else retained("retest_evidence_integrity")
        ),
        "retest_boundary": (
            evidence.candle_end
            if facts.retest and retest_new
            else retained("retest_boundary")
        ),
        "retest_high": (
            source.high if facts.retest and retest_new else retained("retest_high")
        ),
        "retest_low": (
            source.low if facts.retest and retest_new else retained("retest_low")
        ),
        "first_qualification_boundary": (
            evidence.candle_end
            if state is Wo15TimingState.TIMING_QUALIFIED and qualification_new
            else retained("first_qualification_boundary")
        ),
        "first_qualification_at": (
            observed_at
            if state is Wo15TimingState.TIMING_QUALIFIED and qualification_new
            else retained("first_qualification_at")
        ),
        "failure_evidence_identity": (
            evidence.evidence_identity
            if state is Wo15TimingState.TIMING_FAILED
            else retained("failure_evidence_identity")
        ),
        "failure_evidence_integrity": (
            evidence.evidence_integrity
            if state is Wo15TimingState.TIMING_FAILED
            else retained("failure_evidence_integrity")
        ),
        "failure_boundary": (
            evidence.candle_end
            if state is Wo15TimingState.TIMING_FAILED
            else retained("failure_boundary")
        ),
        "failure_at": (
            observed_at
            if state is Wo15TimingState.TIMING_FAILED
            else retained("failure_at")
        ),
        "expiry_cause": expiry_cause or retained("expiry_cause"),
        "expiry_boundary": expiry_boundary or retained("expiry_boundary"),
        "expiry_at": expiry_boundary or retained("expiry_at"),
        "schema_identity": WO15_TIMING_HISTORY_IDENTITY,
        "schema_version": WO15_TIMING_GRAMMAR_VERSION,
    }
    return Wo15TimingLocalHistory(
        history_identity=_identity("INTRADAY-WO15-HISTORY-", values),
        history_integrity=_identity("INTEGRITY-INTRADAY-WO15-HISTORY-", values),
        **values,
    )


def _result(
    *,
    admission: Wo15Wo13Handoff,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
    previous: Wo15TimingEvaluationResult | None,
    prior_state: Wo15TimingState,
    state: Wo15TimingState,
    cause: Wo15TimingCause,
    path: Wo15QualificationPath,
    expiry_cause: Wo15ExpiryCause | None,
    trust_failure: Wo15TrustFailure | None,
    cycle_evaluation: Wo15CycleEvaluation | None,
    local_history: Wo15TimingLocalHistory | None,
    transition_created: bool,
) -> Wo15TimingEvaluationResult:
    values = {
        "timing_cycle_id": (
            cycle_evaluation.cycle.timing_cycle_id
            if cycle_evaluation is not None
            else None
        ),
        "wo13_trade_plan_identity": admission.wo13_trade_plan_identity,
        "prior_result_identity": previous.result_identity if previous is not None else None,
        "prior_state": prior_state,
        "current_state": state,
        "cause": cause,
        "qualification_path": path,
        "evidence_identity": evidence.evidence_identity,
        "evidence_integrity": evidence.evidence_integrity,
        "observation_boundary": evidence.candle_end,
        "progression_identity": progression.adapter_identity,
        "progression_integrity": progression.adapter_integrity,
        "progression_semantics": progression.semantics,
        "expiry_cause": expiry_cause,
        "trust_failure": trust_failure,
        "transition_created": transition_created,
        "cycle_evaluation": cycle_evaluation,
        "local_history": local_history,
        "policy": admission.policy,
        "schema_identity": WO15_TIMING_RESULT_IDENTITY,
        "schema_version": WO15_TIMING_GRAMMAR_VERSION,
        "evaluator_identity": WO15_TIMING_EVALUATOR_IDENTITY,
        "authority": WO15_AUTHORITY,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo15TimingEvaluationResult(
        result_identity=_identity("INTRADAY-WO15-RESULT-", values),
        result_integrity=_identity("INTEGRITY-INTRADAY-WO15-RESULT-", values),
        **values,
    )


def _reset_assessment(
    *,
    predecessor: Wo15TimingEvaluationResult,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
    eligible: bool,
    disposition: Wo15ResetDisposition,
    initial_state: Wo15TimingState | None,
    path: Wo15QualificationPath,
) -> Wo15ResetAssessment:
    cycle = predecessor.cycle_evaluation
    if cycle is None:
        raise Wo15TimingGrammarError("WO15_RESET_PREDECESSOR_INVALID")
    values = {
        "eligible": eligible,
        "disposition": disposition,
        "predecessor_result_identity": predecessor.result_identity,
        "predecessor_cycle_identity": cycle.cycle.timing_cycle_id,
        "predecessor_failure_transition_identity": cycle.transition.transition_identity,
        "predecessor_failure_evidence_identity": (
            cycle.transition.completed_five_minute_evidence_identity
        ),
        "candidate_evidence_identity": evidence.evidence_identity,
        "candidate_evidence_integrity": evidence.evidence_integrity,
        "candidate_boundary": evidence.candle_end,
        "progression_identity": progression.adapter_identity,
        "progression_integrity": progression.adapter_integrity,
        "progression_semantics": progression.semantics,
        "initial_state": initial_state,
        "qualification_path": path,
        "policy": predecessor.policy,
        "schema_identity": WO15_RESET_ASSESSMENT_IDENTITY,
        "schema_version": WO15_TIMING_GRAMMAR_VERSION,
    }
    return Wo15ResetAssessment(
        assessment_identity=_identity("INTRADAY-WO15-RESET-", values),
        assessment_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-RESET-", values
        ),
        **values,
    )


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    material = json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode()
    return prefix + sha256(material).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise Wo15TimingGrammarError("WO15_DECIMAL_INVALID") from error
    if not result.is_finite():
        raise Wo15TimingGrammarError("WO15_DECIMAL_INVALID")
    return result


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _texts(values: tuple[object, ...]) -> bool:
    return bool(values) and all(_text(value) for value in values)


def _optional_text(value: object) -> bool:
    return value is None or _text(value)


def _all_or_none(
    values: tuple[object, ...],
    *,
    text: int = 0,
    aware: int = 0,
    decimal: int = 0,
    enum: type[StrEnum] | None = None,
) -> bool:
    if all(value is None for value in values):
        return True
    if any(value is None for value in values):
        return False
    cursor = 0
    if text and not all(_text(item) for item in values[cursor:cursor + text]):
        return False
    cursor += text
    if enum is not None:
        if type(values[cursor]) is not enum:
            return False
        cursor += 1
    if aware and not all(_aware(item) for item in values[cursor:cursor + aware]):
        return False
    cursor += aware
    if decimal and not all(
        type(item) is Decimal and item.is_finite()
        for item in values[cursor:cursor + decimal]
    ):
        return False
    cursor += decimal
    return cursor == len(values)
