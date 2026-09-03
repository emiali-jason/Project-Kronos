"""Fail-closed exact upstream adapters for Intraday WO-17 Slice 1."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo15 import Wo15TimingState
from kronos.intraday.wo16 import (
    Wo16LifecycleAdmissionDisposition,
    Wo16LifecycleAdmissionRecord,
    Wo16SponsorDecision,
    Wo16SponsorDecisionRecord,
    Wo16SponsorDecisionSnapshot,
)
from kronos.intraday.wo16_persistence import (
    CurrentWo16Pointer,
    Wo16PersistedOperationOutcome,
)
from kronos.market.schedule import MarketSessionState

from .wo17 import (
    Wo17ContractError,
    Wo17UpstreamSnapshot,
    create_wo17_upstream_lineage,
    create_wo17_upstream_snapshot,
)


class Wo17BindingFailure(StrEnum):
    SOURCE_CONTRACT_INVALID = "SOURCE_CONTRACT_INVALID"
    WO16_NOT_CURRENT = "WO16_NOT_CURRENT"
    WO16_DECISION_NOT_ELIGIBLE = "WO16_DECISION_NOT_ELIGIBLE"
    WO16_ADMISSION_NOT_ELIGIBLE = "WO16_ADMISSION_NOT_ELIGIBLE"
    WO13_TRADE_PLAN_MISMATCH = "WO13_TRADE_PLAN_MISMATCH"
    WO14_RISK_OBSERVATION_MISMATCH = "WO14_RISK_OBSERVATION_MISMATCH"
    WO15_HANDOFF_MISMATCH = "WO15_HANDOFF_MISMATCH"
    WO15_TIMING_NOT_QUALIFIED = "WO15_TIMING_NOT_QUALIFIED"
    DOMAIN_008_SESSION_MISMATCH = "DOMAIN_008_SESSION_MISMATCH"
    DOMAIN_008_SESSION_ENDED = "DOMAIN_008_SESSION_ENDED"
    DOMAIN_008_SESSION_NOT_OPEN = "DOMAIN_008_SESSION_NOT_OPEN"
    CANONICAL_SUBJECT_MISMATCH = "CANONICAL_SUBJECT_MISMATCH"
    INSTRUMENT_MISMATCH = "INSTRUMENT_MISMATCH"
    NSE_MCX_LINEAGE_PROHIBITED = "NSE_MCX_LINEAGE_PROHIBITED"
    MCX_CONTRACT_LINEAGE_MISSING = "MCX_CONTRACT_LINEAGE_MISSING"
    MCX_CONTRACT_LINEAGE_MISMATCH = "MCX_CONTRACT_LINEAGE_MISMATCH"
    POLICY_MISMATCH = "POLICY_MISMATCH"
    NON_CLOSED_POSITION_EXISTS = "NON_CLOSED_POSITION_EXISTS"


class Wo17BindingRejected(Wo17ContractError):
    def __init__(self, failure: Wo17BindingFailure) -> None:
        if type(failure) is not Wo17BindingFailure:
            raise Wo17ContractError("WO17_BINDING_FAILURE_INVALID")
        self.failure = failure
        super().__init__(failure.value)


def bind_wo17_upstream(
    *,
    current_pointer: CurrentWo16Pointer,
    snapshot: Wo16SponsorDecisionSnapshot,
    decision: Wo16SponsorDecisionRecord,
    admission: Wo16LifecycleAdmissionRecord,
    bound_at: datetime,
    existing_non_closed_position_identity: str | None = None,
    provenance: tuple[str, ...] = ("ADR-0027", "WO-17-SLICE-1"),
) -> Wo17UpstreamSnapshot:
    """Bind a current admitted graph without creating position truth."""

    if (
        type(current_pointer) is not CurrentWo16Pointer
        or type(snapshot) is not Wo16SponsorDecisionSnapshot
        or type(decision) is not Wo16SponsorDecisionRecord
        or type(admission) is not Wo16LifecycleAdmissionRecord
        or not _aware(bound_at)
    ):
        _reject(Wo17BindingFailure.SOURCE_CONTRACT_INVALID)
    for source in (current_pointer, snapshot, decision, admission):
        _validate_source(source)
    if existing_non_closed_position_identity is not None:
        if not _text(existing_non_closed_position_identity):
            _reject(Wo17BindingFailure.SOURCE_CONTRACT_INVALID)
        _reject(Wo17BindingFailure.NON_CLOSED_POSITION_EXISTS)

    lineage = snapshot.upstream_lineage
    for source in (
        lineage,
        lineage.trade_plan,
        lineage.risk_observation,
        lineage.timing_handoff,
        lineage.session,
        lineage.policy,
    ):
        _validate_source(source)
    trade = lineage.trade_plan
    risk = lineage.risk_observation
    timing = lineage.timing_handoff
    session = lineage.session

    if (
        current_pointer.operation_outcome
        is not Wo16PersistedOperationOutcome.COMPLETED
        or current_pointer.snapshot_identity != snapshot.snapshot_identity
        or current_pointer.snapshot_integrity != snapshot.snapshot_integrity
        or current_pointer.decision_identity != decision.decision_identity
        or current_pointer.decision_integrity != decision.decision_integrity
        or current_pointer.admission_identity != admission.admission_identity
        or current_pointer.admission_integrity != admission.admission_integrity
        or decision.snapshot_identity != snapshot.snapshot_identity
        or decision.snapshot_integrity != snapshot.snapshot_integrity
        or admission.decision_identity != decision.decision_identity
        or admission.decision_integrity != decision.decision_integrity
    ):
        _reject(Wo17BindingFailure.WO16_NOT_CURRENT)
    if decision.choice not in {Wo16SponsorDecision.PAPER, Wo16SponsorDecision.LIVE}:
        _reject(Wo17BindingFailure.WO16_DECISION_NOT_ELIGIBLE)
    if (
        admission.disposition
        is not Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE
    ):
        _reject(Wo17BindingFailure.WO16_ADMISSION_NOT_ELIGIBLE)
    if decision.timing_handoff_identity != timing.handoff_identity:
        _reject(Wo17BindingFailure.WO15_HANDOFF_MISMATCH)
    if timing.current_state is not Wo15TimingState.TIMING_QUALIFIED:
        _reject(Wo17BindingFailure.WO15_TIMING_NOT_QUALIFIED)

    if (
        current_pointer.wo13_trade_plan_identity != trade.trade_plan_identity
        or current_pointer.wo13_trade_plan_integrity != trade.trade_plan_integrity
        or risk.trade_plan_identity != trade.trade_plan_identity
        or risk.trade_plan_integrity != trade.trade_plan_integrity
        or timing.trade_plan_identity != trade.trade_plan_identity
        or timing.trade_plan_integrity != trade.trade_plan_integrity
    ):
        _reject(Wo17BindingFailure.WO13_TRADE_PLAN_MISMATCH)
    if (
        current_pointer.wo14_observation_identity != risk.observation_identity
        or current_pointer.wo14_observation_integrity != risk.observation_integrity
        or risk.trade_permission_authority
        or risk.trade_veto_authority
    ):
        _reject(Wo17BindingFailure.WO14_RISK_OBSERVATION_MISMATCH)
    if (
        current_pointer.wo15_handoff_identity != timing.handoff_identity
        or current_pointer.wo15_handoff_integrity != timing.handoff_integrity
    ):
        _reject(Wo17BindingFailure.WO15_HANDOFF_MISMATCH)

    canonical_values = (
        (current_pointer.canonical_subject_identity, trade.canonical_subject_identity),
        (current_pointer.market_family, trade.market_family),
    )
    if any(left != right for left, right in canonical_values):
        _reject(Wo17BindingFailure.CANONICAL_SUBJECT_MISMATCH)
    if (
        current_pointer.instrument_identity != trade.instrument_identity
        or timing.instrument_identity != trade.instrument_identity
    ):
        _reject(Wo17BindingFailure.INSTRUMENT_MISMATCH)

    session_pairs = (
        (current_pointer.trading_date, session.trading_date),
        (current_pointer.session_identity, session.session_identity),
        (current_pointer.calendar_identity, session.calendar_identity),
        (current_pointer.calendar_version, session.calendar_version),
        (
            current_pointer.domain_008_session_binding_identity,
            session.binding_identity,
        ),
        (
            current_pointer.domain_008_session_binding_integrity,
            session.binding_integrity,
        ),
        (timing.session_identity, session.session_identity),
        (timing.calendar_identity, session.calendar_identity),
        (timing.calendar_version, session.calendar_version),
    )
    if any(left != right for left, right in session_pairs):
        _reject(Wo17BindingFailure.DOMAIN_008_SESSION_MISMATCH)
    if bound_at >= session.active_window_closes_at:
        _reject(Wo17BindingFailure.DOMAIN_008_SESSION_ENDED)
    if (
        session.market_session_state is not MarketSessionState.OPEN
        or session.session_open is not True
        or session.session_end is not False
        or bound_at < session.active_window_opens_at
        or bound_at.date() != session.trading_date
    ):
        _reject(Wo17BindingFailure.DOMAIN_008_SESSION_NOT_OPEN)

    mcx = trade.market_family is IntradayMarketFamily.MCX
    source_mcx = (
        trade.actual_contract_identity,
        trade.contract_expiry,
        trade.roll_lineage_identity,
    )
    pointer_mcx = (
        current_pointer.actual_contract_identity,
        current_pointer.contract_expiry,
        current_pointer.roll_lineage_identity,
    )
    timing_mcx = (timing.actual_contract_identity, timing.roll_lineage_identity)
    if mcx and (not all(value is not None for value in source_mcx)):
        _reject(Wo17BindingFailure.MCX_CONTRACT_LINEAGE_MISSING)
    if not mcx and (
        any(value is not None for value in source_mcx)
        or any(value is not None for value in pointer_mcx)
        or any(value is not None for value in timing_mcx)
    ):
        _reject(Wo17BindingFailure.NSE_MCX_LINEAGE_PROHIBITED)
    if mcx and (
        pointer_mcx != source_mcx
        or timing.actual_contract_identity != trade.actual_contract_identity
        or timing.roll_lineage_identity != trade.roll_lineage_identity
    ):
        _reject(Wo17BindingFailure.MCX_CONTRACT_LINEAGE_MISMATCH)

    if current_pointer.policy != snapshot.policy or snapshot.policy != lineage.policy:
        _reject(Wo17BindingFailure.POLICY_MISMATCH)
    if not (
        snapshot.snapshot_timestamp
        <= decision.decision_timestamp
        <= admission.recorded_at
        <= current_pointer.published_at
        <= bound_at
    ):
        _reject(Wo17BindingFailure.WO16_NOT_CURRENT)

    wo17_lineage = create_wo17_upstream_lineage(
        current_wo16_pointer_identity=current_pointer.pointer_identity,
        current_wo16_pointer_integrity=current_pointer.pointer_integrity,
        wo13_trade_plan_identity=trade.trade_plan_identity,
        wo13_trade_plan_integrity=trade.trade_plan_integrity,
        wo14_observation_identity=risk.observation_identity,
        wo14_observation_integrity=risk.observation_integrity,
        wo15_handoff_identity=timing.handoff_identity,
        wo15_handoff_integrity=timing.handoff_integrity,
        wo16_snapshot_identity=snapshot.snapshot_identity,
        wo16_snapshot_integrity=snapshot.snapshot_integrity,
        wo16_decision_identity=decision.decision_identity,
        wo16_decision_integrity=decision.decision_integrity,
        wo16_admission_identity=admission.admission_identity,
        wo16_admission_integrity=admission.admission_integrity,
        domain_008_session_binding_identity=session.binding_identity,
        domain_008_session_binding_integrity=session.binding_integrity,
        canonical_subject_identity=trade.canonical_subject_identity,
        market_family=trade.market_family,
        direction=trade.direction,
        setup_family=trade.setup_family,
        instrument_identity=trade.instrument_identity,
        actual_contract_identity=trade.actual_contract_identity,
        contract_expiry=trade.contract_expiry,
        roll_lineage_identity=trade.roll_lineage_identity,
        trading_date=session.trading_date,
        session_identity=session.session_identity,
        calendar_identity=session.calendar_identity,
        calendar_version=session.calendar_version,
        active_window_opens_at=session.active_window_opens_at,
        active_window_closes_at=session.active_window_closes_at,
        entry_reference=trade.entry_reference,
        entry_condition=trade.entry_condition,
        stop=trade.stop,
        thesis_invalidation_reference=trade.thesis_invalidation_reference,
        thesis_invalidation_event=trade.thesis_invalidation_event,
        canonical_target=trade.canonical_target,
        risk_distance=trade.risk_distance,
        reward_distance=trade.reward_distance,
        model_rr=trade.model_rr,
        risk_observation_state=risk.state,
        timing_state=timing.current_state,
        timing_evidence_boundary=timing.evidence_boundary,
        sponsor_decision=decision.choice,
        lifecycle_admission=admission.disposition,
        wo13_policy_identity=trade.wo13_policy_identity,
        wo13_policy_version=trade.wo13_policy_version,
        wo13_policy_checksum=trade.wo13_policy_checksum,
        wo14_policy_identity=risk.wo14_policy_identity,
        wo14_policy_version=risk.wo14_policy_version,
        wo14_policy_checksum=risk.wo14_policy_checksum,
        wo15_policy_identity=timing.wo15_policy_identity,
        wo15_policy_version=timing.wo15_policy_version,
        wo15_policy_checksum=timing.wo15_policy_checksum,
        wo16_policy_identity=snapshot.policy.policy_identity,
        wo16_policy_version=snapshot.policy.policy_version,
        wo16_policy_checksum=snapshot.policy.policy_checksum,
        provenance=provenance,
    )
    return create_wo17_upstream_snapshot(
        lineage=wo17_lineage,
        bound_at=bound_at,
        provenance=provenance,
    )


def _validate_source(value: object) -> None:
    try:
        value.__post_init__()  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError) as error:
        raise Wo17BindingRejected(Wo17BindingFailure.SOURCE_CONTRACT_INVALID) from error


def _reject(failure: Wo17BindingFailure) -> None:
    raise Wo17BindingRejected(failure)


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


__all__ = [
    "Wo17BindingFailure",
    "Wo17BindingRejected",
    "bind_wo17_upstream",
]
