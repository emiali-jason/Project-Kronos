"""Pure exact-lineage adapters for Intraday WO-16 Slice 1.

The adapters only validate and bind already-produced immutable upstream facts.
They do not calculate geometry or Risk, rerun timing, inspect a clock, call a
Provider, persist evidence, or execute a Sponsor decision.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import (
    CurrentWo13Pointer,
    Wo13GeometryAvailability,
    Wo13TradePlan,
)
from kronos.intraday.wo13_handoff import Wo13Step31Handoff
from kronos.intraday.wo14 import (
    CurrentWo14Pointer,
    Wo14ObservationState,
    Wo14RiskObservation,
)
from kronos.intraday.wo15 import (
    Wo15PolicyBinding,
    Wo15SessionBinding,
    Wo15TimingState,
)
from kronos.intraday.wo15_handoff import Wo15TimingHandoff
from kronos.market.schedule import (
    MarketSessionFact,
    MarketSessionState,
    TradingDayStatus,
)

from .wo16 import (
    WO16_CONTRACT_VERSION,
    WO16_SESSION_BINDING_IDENTITY,
    WO16_WO13_BINDING_IDENTITY,
    WO16_WO14_BINDING_IDENTITY,
    WO16_WO15_BINDING_IDENTITY,
    Wo16ContractError,
    Wo16FactAvailability,
    Wo16RiskObservationBinding,
    Wo16SessionFactBinding,
    Wo16TimingHandoffBinding,
    Wo16TradePlanBinding,
    Wo16UpstreamLineage,
    canonical_document_bytes,
    canonical_sha256,
    create_wo16_upstream_lineage,
)


class Wo16BindingFailure(StrEnum):
    WO13_NOT_CURRENT = "WO13_NOT_CURRENT"
    WO13_INTEGRITY_INVALID = "WO13_INTEGRITY_INVALID"
    WO13_GEOMETRY_INCOMPLETE = "WO13_GEOMETRY_INCOMPLETE"
    WO14_NOT_CURRENT = "WO14_NOT_CURRENT"
    WO14_INTEGRITY_INVALID = "WO14_INTEGRITY_INVALID"
    WO14_PLAN_MISMATCH = "WO14_PLAN_MISMATCH"
    WO15_NOT_CURRENT = "WO15_NOT_CURRENT"
    WO15_INTEGRITY_INVALID = "WO15_INTEGRITY_INVALID"
    WO15_TIMING_NOT_QUALIFIED = "WO15_TIMING_NOT_QUALIFIED"
    WO15_SESSION_STALE = "WO15_SESSION_STALE"
    DOMAIN_008_UNAVAILABLE = "DOMAIN_008_UNAVAILABLE"
    DOMAIN_008_NON_TRADING_DAY = "DOMAIN_008_NON_TRADING_DAY"
    DOMAIN_008_NOT_OPEN = "DOMAIN_008_NOT_OPEN"
    DOMAIN_008_SESSION_ENDED = "DOMAIN_008_SESSION_ENDED"
    EXCHANGE_MISMATCH = "EXCHANGE_MISMATCH"
    TRADING_DATE_MISMATCH = "TRADING_DATE_MISMATCH"
    SESSION_IDENTITY_MISMATCH = "SESSION_IDENTITY_MISMATCH"
    CALENDAR_IDENTITY_MISMATCH = "CALENDAR_IDENTITY_MISMATCH"
    CALENDAR_VERSION_MISMATCH = "CALENDAR_VERSION_MISMATCH"
    CANONICAL_LINEAGE_MISMATCH = "CANONICAL_LINEAGE_MISMATCH"
    INSTRUMENT_LINEAGE_MISMATCH = "INSTRUMENT_LINEAGE_MISMATCH"
    MCX_CONTRACT_LINEAGE_MISSING = "MCX_CONTRACT_LINEAGE_MISSING"
    MCX_CONTRACT_LINEAGE_MISMATCH = "MCX_CONTRACT_LINEAGE_MISMATCH"
    POLICY_MISMATCH = "POLICY_MISMATCH"
    SOURCE_EVIDENCE_INVALID = "SOURCE_EVIDENCE_INVALID"


class Wo16BindingRejected(Wo16ContractError):
    """Fail-closed, sanitized exact-boundary rejection."""

    def __init__(self, failure: Wo16BindingFailure) -> None:
        if type(failure) is not Wo16BindingFailure:
            raise Wo16ContractError("WO16_BINDING_FAILURE_INVALID")
        self.failure = failure
        super().__init__(failure.value)


class Wo16CurrentWo15Pointer(Protocol):
    """Persistence-neutral view of the validated current WO-15 pointer."""

    pointer_identity: str
    pointer_integrity: str
    wo13_trade_plan_identity: str
    wo13_trade_plan_integrity: str
    timing_handoff_identity: str | None
    timing_handoff_integrity: str | None
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    direction: object
    setup_family: object
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    calendar_identity: str
    calendar_version: str
    timing_state: Wo15TimingState
    policy: Wo15PolicyBinding
    published_at: datetime

    def __post_init__(self) -> None: ...


def bind_wo16_trade_plan(
    *,
    current_pointer: CurrentWo13Pointer,
    trade_plan: Wo13TradePlan,
    source_handoff: Wo13Step31Handoff,
    provenance: tuple[str, ...] = ("ADR-0026", "WO-16-SLICE-1"),
) -> Wo16TradePlanBinding:
    """Bind the exact current complete WO-13 plan without recalculation."""

    if (
        type(current_pointer) is not CurrentWo13Pointer
        or type(trade_plan) is not Wo13TradePlan
        or type(source_handoff) is not Wo13Step31Handoff
    ):
        _reject(Wo16BindingFailure.SOURCE_EVIDENCE_INVALID)
    _validate_source(current_pointer, Wo16BindingFailure.WO13_INTEGRITY_INVALID)
    _validate_source(trade_plan, Wo16BindingFailure.WO13_INTEGRITY_INVALID)
    _validate_source(source_handoff, Wo16BindingFailure.WO13_INTEGRITY_INVALID)

    pointer_pairs = (
        (current_pointer.trade_plan_identity, trade_plan.trade_plan_identity),
        (current_pointer.trade_plan_integrity, trade_plan.trade_plan_integrity),
        (current_pointer.request_identity, trade_plan.request_identity),
        (current_pointer.request_integrity, trade_plan.request_integrity),
        (current_pointer.handoff_identity, trade_plan.source_handoff_identity),
        (current_pointer.handoff_integrity, trade_plan.source_handoff_integrity),
        (
            current_pointer.canonical_subject_identity,
            trade_plan.canonical_subject_identity,
        ),
        (current_pointer.market_family, trade_plan.market_family),
        (current_pointer.direction, trade_plan.direction),
        (current_pointer.setup_family, trade_plan.setup_family),
    )
    if any(left != right for left, right in pointer_pairs):
        _reject(Wo16BindingFailure.WO13_NOT_CURRENT)
    source_pairs = (
        (source_handoff.handoff_identity, trade_plan.source_handoff_identity),
        (source_handoff.handoff_integrity, trade_plan.source_handoff_integrity),
        (source_handoff.canonical_subject_identity, trade_plan.canonical_subject_identity),
        (source_handoff.market_family, trade_plan.market_family),
        (source_handoff.inherited_direction, trade_plan.direction),
        (source_handoff.setup_family, trade_plan.setup_family),
        (source_handoff.instrument_identity, trade_plan.instrument_identity),
        (source_handoff.actual_contract_identity, trade_plan.actual_contract_identity),
    )
    if any(left != right for left, right in source_pairs):
        _reject(Wo16BindingFailure.CANONICAL_LINEAGE_MISMATCH)
    if trade_plan.geometry_availability is not Wo13GeometryAvailability.GEOMETRY_COMPLETE:
        _reject(Wo16BindingFailure.WO13_GEOMETRY_INCOMPLETE)
    geometry = (
        trade_plan.entry_reference,
        trade_plan.entry_condition,
        trade_plan.stop,
        trade_plan.thesis_invalidation_reference,
        trade_plan.thesis_invalidation_event,
        trade_plan.canonical_target,
        trade_plan.risk_distance,
        trade_plan.reward_distance,
        trade_plan.model_rr,
    )
    if any(value is None for value in geometry):
        _reject(Wo16BindingFailure.WO13_GEOMETRY_INCOMPLETE)
    if current_pointer.policy != trade_plan.policy:
        _reject(Wo16BindingFailure.POLICY_MISMATCH)

    mcx = trade_plan.market_family is IntradayMarketFamily.MCX
    mcx_values = (
        source_handoff.actual_contract_identity,
        source_handoff.contract_expiry,
        source_handoff.roll_lineage_identity,
    )
    if mcx and any(value is None for value in mcx_values):
        _reject(Wo16BindingFailure.MCX_CONTRACT_LINEAGE_MISSING)
    if not mcx and any(value is not None for value in mcx_values):
        _reject(Wo16BindingFailure.MCX_CONTRACT_LINEAGE_MISMATCH)

    values = {
        "current_pointer_identity": current_pointer.pointer_identity,
        "current_pointer_integrity": current_pointer.pointer_integrity,
        "trade_plan_identity": trade_plan.trade_plan_identity,
        "trade_plan_integrity": trade_plan.trade_plan_integrity,
        "source_handoff_identity": source_handoff.handoff_identity,
        "source_handoff_integrity": source_handoff.handoff_integrity,
        "canonical_subject_identity": trade_plan.canonical_subject_identity,
        "market_family": trade_plan.market_family,
        "direction": trade_plan.direction,
        "setup_family": trade_plan.setup_family,
        "instrument_identity": trade_plan.instrument_identity,
        "actual_contract_identity": source_handoff.actual_contract_identity,
        "contract_expiry": source_handoff.contract_expiry,
        "roll_lineage_identity": source_handoff.roll_lineage_identity,
        "geometry_availability": trade_plan.geometry_availability,
        "entry_reference": trade_plan.entry_reference,
        "entry_condition": trade_plan.entry_condition,
        "stop": trade_plan.stop,
        "thesis_invalidation_reference": trade_plan.thesis_invalidation_reference,
        "thesis_invalidation_event": trade_plan.thesis_invalidation_event,
        "canonical_target": trade_plan.canonical_target,
        "risk_distance": trade_plan.risk_distance,
        "reward_distance": trade_plan.reward_distance,
        "model_rr": trade_plan.model_rr,
        "wo13_policy_identity": trade_plan.policy.policy_identity,
        "wo13_policy_version": trade_plan.policy.policy_version,
        "wo13_policy_checksum": trade_plan.policy.policy_checksum,
        "source_evidence_identities": trade_plan.source_evidence_identities,
        "source_evidence_integrities": trade_plan.source_evidence_integrities,
        "provenance": provenance,
        "schema_identity": WO16_WO13_BINDING_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
        "geometry_authority": False,
        "risk_authority": False,
        "timing_authority": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo16TradePlanBinding(
        binding_identity=_identity("INTRADAY-WO16-WO13-BINDING-", values),
        binding_integrity=_identity(
            "INTEGRITY-INTRADAY-WO16-WO13-BINDING-", values
        ),
        **values,
    )


def bind_wo16_risk_observation(
    *,
    current_pointer: CurrentWo14Pointer,
    observation: Wo14RiskObservation,
    trade_plan: Wo16TradePlanBinding,
    provenance: tuple[str, ...] = ("ADR-0026", "WO-16-SLICE-1"),
) -> Wo16RiskObservationBinding:
    """Bind advisory WO-14 evidence; all states remain non-veto."""

    if (
        type(current_pointer) is not CurrentWo14Pointer
        or type(observation) is not Wo14RiskObservation
        or type(trade_plan) is not Wo16TradePlanBinding
    ):
        _reject(Wo16BindingFailure.SOURCE_EVIDENCE_INVALID)
    _validate_source(current_pointer, Wo16BindingFailure.WO14_INTEGRITY_INVALID)
    _validate_source(observation, Wo16BindingFailure.WO14_INTEGRITY_INVALID)
    pointer_pairs = (
        (current_pointer.observation_identity, observation.observation_identity),
        (current_pointer.observation_integrity, observation.observation_integrity),
        (current_pointer.trade_plan_identity, trade_plan.trade_plan_identity),
        (current_pointer.trade_plan_integrity, trade_plan.trade_plan_integrity),
        (current_pointer.canonical_subject_identity, trade_plan.canonical_subject_identity),
        (current_pointer.market_family, trade_plan.market_family),
        (current_pointer.state, observation.state),
    )
    if any(left != right for left, right in pointer_pairs):
        _reject(Wo16BindingFailure.WO14_NOT_CURRENT)
    plan_binding = observation.plan_binding
    plan_pairs = (
        (plan_binding.trade_plan_identity, trade_plan.trade_plan_identity),
        (plan_binding.trade_plan_integrity, trade_plan.trade_plan_integrity),
        (plan_binding.canonical_subject_identity, trade_plan.canonical_subject_identity),
        (plan_binding.market_family, trade_plan.market_family),
        (plan_binding.direction, trade_plan.direction),
        (plan_binding.setup_family, trade_plan.setup_family),
        (plan_binding.instrument_identity, trade_plan.instrument_identity),
        (plan_binding.actual_contract_identity, trade_plan.actual_contract_identity),
    )
    if any(left != right for left, right in plan_pairs):
        _reject(Wo16BindingFailure.WO14_PLAN_MISMATCH)
    if current_pointer.policy != observation.policy:
        _reject(Wo16BindingFailure.POLICY_MISMATCH)
    if any(
        (
            observation.trade_permission_authority,
            observation.wo15_blocking_authority,
            observation.final_quantity_authority,
            observation.sponsor_decision_authority,
            observation.execution_authority,
            observation.broker_authority,
        )
    ):
        _reject(Wo16BindingFailure.WO14_INTEGRITY_INVALID)

    values = {
        "current_pointer_identity": current_pointer.pointer_identity,
        "current_pointer_integrity": current_pointer.pointer_integrity,
        "observation_identity": observation.observation_identity,
        "observation_integrity": observation.observation_integrity,
        "trade_plan_identity": trade_plan.trade_plan_identity,
        "trade_plan_integrity": trade_plan.trade_plan_integrity,
        "state": observation.state,
        "calculation_provenance_integrity": canonical_sha256(
            observation.calculation_provenance
        ),
        "wo14_policy_identity": observation.policy.policy_identity,
        "wo14_policy_version": observation.policy.policy_version,
        "wo14_policy_checksum": observation.policy.policy_checksum,
        "provenance": provenance,
        "schema_identity": WO16_WO14_BINDING_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
        "authority": "RISK_OBSERVATION_ONLY",
        "trade_permission_authority": False,
        "trade_veto_authority": False,
        "timing_authority": False,
        "sizing_authority": False,
        "final_quantity_authority": False,
        "execution_authority": False,
    }
    return Wo16RiskObservationBinding(
        binding_identity=_identity("INTRADAY-WO16-WO14-BINDING-", values),
        binding_integrity=_identity(
            "INTEGRITY-INTRADAY-WO16-WO14-BINDING-", values
        ),
        **values,
    )


def is_wo16_risk_state_admissible(state: object) -> bool:
    """WO-14 availability/severity is advisory and never a permission gate."""

    if type(state) is not Wo14ObservationState:
        _reject(Wo16BindingFailure.WO14_INTEGRITY_INVALID)
    return state in {
        Wo14ObservationState.RISK_OBSERVED,
        Wo14ObservationState.RISK_ALERT,
        Wo14ObservationState.RISK_UNAVAILABLE,
    }


def bind_wo16_timing_handoff(
    *,
    current_pointer: Wo16CurrentWo15Pointer,
    handoff: Wo15TimingHandoff,
    trade_plan: Wo16TradePlanBinding,
    risk_observation: Wo16RiskObservationBinding,
    provenance: tuple[str, ...] = ("ADR-0026", "WO-16-SLICE-1"),
) -> Wo16TimingHandoffBinding:
    """Bind only the exact current TIMING_QUALIFIED WO-15 handoff."""

    if (
        type(handoff) is not Wo15TimingHandoff
        or type(trade_plan) is not Wo16TradePlanBinding
        or type(risk_observation) is not Wo16RiskObservationBinding
    ):
        _reject(Wo16BindingFailure.SOURCE_EVIDENCE_INVALID)
    _validate_source(current_pointer, Wo16BindingFailure.WO15_INTEGRITY_INVALID)
    _validate_source(handoff, Wo16BindingFailure.WO15_INTEGRITY_INVALID)
    if not is_wo16_timing_state_eligible(
        current_pointer.timing_state
    ) or not is_wo16_timing_state_eligible(handoff.current_state):
        _reject(Wo16BindingFailure.WO15_TIMING_NOT_QUALIFIED)
    pointer_pairs = (
        (current_pointer.timing_handoff_identity, handoff.handoff_identity),
        (current_pointer.timing_handoff_integrity, handoff.handoff_integrity),
        (current_pointer.wo13_trade_plan_identity, trade_plan.trade_plan_identity),
        (current_pointer.wo13_trade_plan_integrity, trade_plan.trade_plan_integrity),
        (current_pointer.canonical_subject_identity, trade_plan.canonical_subject_identity),
        (current_pointer.market_family, trade_plan.market_family),
        (current_pointer.direction, trade_plan.direction),
        (current_pointer.setup_family, trade_plan.setup_family),
        (current_pointer.instrument_identity, trade_plan.instrument_identity),
        (current_pointer.actual_contract_identity, trade_plan.actual_contract_identity),
        (current_pointer.roll_lineage_identity, trade_plan.roll_lineage_identity),
        (current_pointer.session_identity, handoff.session_identity),
        (current_pointer.calendar_identity, handoff.calendar_identity),
        (current_pointer.calendar_version, handoff.calendar_version),
    )
    if any(left != right for left, right in pointer_pairs):
        _reject(Wo16BindingFailure.WO15_NOT_CURRENT)
    handoff_pairs = (
        (handoff.wo13_trade_plan_identity, trade_plan.trade_plan_identity),
        (handoff.wo13_trade_plan_integrity, trade_plan.trade_plan_integrity),
        (handoff.direction, trade_plan.direction),
        (handoff.setup_family, trade_plan.setup_family),
        (handoff.instrument_identity, trade_plan.instrument_identity),
        (handoff.actual_contract_identity, trade_plan.actual_contract_identity),
        (handoff.roll_lineage_identity, trade_plan.roll_lineage_identity),
    )
    if any(left != right for left, right in handoff_pairs):
        _reject(Wo16BindingFailure.CANONICAL_LINEAGE_MISMATCH)
    if current_pointer.policy.policy_identity != handoff.policy_identity or (
        current_pointer.policy.policy_version != handoff.policy_version
        or current_pointer.policy.policy_checksum != handoff.policy_checksum
    ):
        _reject(Wo16BindingFailure.POLICY_MISMATCH)
    if handoff.wo14_observation_identity is not None and (
        handoff.wo14_observation_identity != risk_observation.observation_identity
        or handoff.wo14_observation_integrity != risk_observation.observation_integrity
    ):
        _reject(Wo16BindingFailure.WO14_PLAN_MISMATCH)

    values = {
        "current_pointer_identity": current_pointer.pointer_identity,
        "current_pointer_integrity": current_pointer.pointer_integrity,
        "handoff_identity": handoff.handoff_identity,
        "handoff_integrity": handoff.handoff_integrity,
        "trade_plan_identity": handoff.wo13_trade_plan_identity,
        "trade_plan_integrity": handoff.wo13_trade_plan_integrity,
        "timing_cycle_identity": handoff.timing_cycle_id,
        "timing_cycle_integrity": handoff.timing_cycle_integrity,
        "timing_observation_identity": handoff.timing_observation_identity,
        "timing_observation_integrity": handoff.timing_observation_integrity,
        "timing_transition_identity": handoff.timing_transition_identity,
        "timing_transition_integrity": handoff.timing_transition_integrity,
        "prior_state": handoff.prior_state,
        "current_state": handoff.current_state,
        "transition_cause": handoff.transition_cause,
        "qualification_path": handoff.qualification_path,
        "completed_five_minute_evidence_identity": (
            handoff.completed_five_minute_evidence_identity
        ),
        "completed_five_minute_evidence_integrity": (
            handoff.completed_five_minute_evidence_integrity
        ),
        "evidence_boundary": handoff.evidence_boundary,
        "session_identity": handoff.session_identity,
        "calendar_identity": handoff.calendar_identity,
        "calendar_version": handoff.calendar_version,
        "instrument_identity": handoff.instrument_identity,
        "actual_contract_identity": handoff.actual_contract_identity,
        "roll_lineage_identity": handoff.roll_lineage_identity,
        "wo15_policy_identity": handoff.policy_identity,
        "wo15_policy_version": handoff.policy_version,
        "wo15_policy_checksum": handoff.policy_checksum,
        "wo14_observation_identity": handoff.wo14_observation_identity,
        "wo14_observation_integrity": handoff.wo14_observation_integrity,
        "predecessor_handoff_identity": handoff.predecessor_handoff_identity,
        "supersession_lineage_identity": handoff.supersession_lineage_identity,
        "provenance": provenance,
        "schema_identity": WO16_WO15_BINDING_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
        "timing_evidence_authority": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo16TimingHandoffBinding(
        binding_identity=_identity("INTRADAY-WO16-WO15-BINDING-", values),
        binding_integrity=_identity(
            "INTEGRITY-INTRADAY-WO16-WO15-BINDING-", values
        ),
        **values,
    )


def is_wo16_timing_state_eligible(state: Wo15TimingState) -> bool:
    """Return eligibility for an explicit governed state; infer nothing."""

    if type(state) is not Wo15TimingState:
        _reject(Wo16BindingFailure.WO15_TIMING_NOT_QUALIFIED)
    return state is Wo15TimingState.TIMING_QUALIFIED


def bind_wo16_session_fact(
    *,
    wo15_session: Wo15SessionBinding,
    fact: MarketSessionFact,
    timing_handoff: Wo16TimingHandoffBinding,
    provenance: tuple[str, ...] = ("ADR-0026", "DOMAIN-008"),
) -> Wo16SessionFactBinding:
    """Bind an explicitly supplied current open DOMAIN-008 fact."""

    if (
        type(wo15_session) is not Wo15SessionBinding
        or type(fact) is not MarketSessionFact
        or type(timing_handoff) is not Wo16TimingHandoffBinding
    ):
        _reject(Wo16BindingFailure.SOURCE_EVIDENCE_INVALID)
    _validate_source(wo15_session, Wo16BindingFailure.WO15_INTEGRITY_INVALID)
    _validate_source(fact, Wo16BindingFailure.DOMAIN_008_UNAVAILABLE)
    if not fact.availability or fact.schedule is None:
        _reject(Wo16BindingFailure.DOMAIN_008_UNAVAILABLE)
    if fact.state is MarketSessionState.NON_TRADING_DAY or (
        fact.schedule.status is TradingDayStatus.NON_TRADING
    ):
        _reject(Wo16BindingFailure.DOMAIN_008_NON_TRADING_DAY)
    if fact.session_end:
        _reject(Wo16BindingFailure.DOMAIN_008_SESSION_ENDED)
    if fact.state is not MarketSessionState.OPEN or fact.active_window is None:
        _reject(Wo16BindingFailure.DOMAIN_008_NOT_OPEN)
    schedule = fact.schedule
    expected_exchange = (
        "MCX"
        if timing_handoff.actual_contract_identity is not None
        else "NSE"
    )
    if fact.exchange != expected_exchange or wo15_session.exchange != expected_exchange:
        _reject(Wo16BindingFailure.EXCHANGE_MISMATCH)
    if fact.trading_date != wo15_session.trading_date:
        _reject(Wo16BindingFailure.TRADING_DATE_MISMATCH)
    if schedule.session_id != wo15_session.session_identity or (
        timing_handoff.session_identity != wo15_session.session_identity
    ):
        _reject(Wo16BindingFailure.SESSION_IDENTITY_MISMATCH)
    if schedule.source_identity != wo15_session.calendar_identity or (
        timing_handoff.calendar_identity != wo15_session.calendar_identity
    ):
        _reject(Wo16BindingFailure.CALENDAR_IDENTITY_MISMATCH)
    if schedule.source_version != wo15_session.calendar_version or (
        timing_handoff.calendar_version != wo15_session.calendar_version
    ):
        _reject(Wo16BindingFailure.CALENDAR_VERSION_MISMATCH)
    if fact.observed_at.date() != fact.trading_date:
        _reject(Wo16BindingFailure.TRADING_DATE_MISMATCH)

    values = {
        "wo15_session_binding_identity": wo15_session.binding_identity,
        "wo15_session_binding_integrity": wo15_session.binding_integrity,
        "exchange": fact.exchange,
        "trading_date": fact.trading_date,
        "session_identity": schedule.session_id,
        "calendar_identity": schedule.source_identity,
        "calendar_version": schedule.source_version,
        "market_session_state": fact.state,
        "active_window_opens_at": fact.active_window.opens_at,
        "active_window_closes_at": fact.active_window.closes_at,
        "observed_at": fact.observed_at,
        "availability": Wo16FactAvailability.AVAILABLE,
        "session_open": True,
        "session_end": False,
        "source_identity": schedule.source_identity,
        "source_version": schedule.source_version,
        "provenance": provenance,
        "schema_identity": WO16_SESSION_BINDING_IDENTITY,
        "schema_version": WO16_CONTRACT_VERSION,
    }
    return Wo16SessionFactBinding(
        binding_identity=_identity("INTRADAY-WO16-SESSION-BINDING-", values),
        binding_integrity=_identity(
            "INTEGRITY-INTRADAY-WO16-SESSION-BINDING-", values
        ),
        **values,
    )


def bind_wo16_upstream(
    *,
    trade_plan: Wo16TradePlanBinding,
    risk_observation: Wo16RiskObservationBinding,
    timing_handoff: Wo16TimingHandoffBinding,
    session: Wo16SessionFactBinding,
    provenance: tuple[str, ...] = ("ADR-0026", "WO-16-SLICE-1"),
) -> Wo16UpstreamLineage:
    """Validate the complete exact graph and return one immutable lineage."""

    if not all(
        (
            type(trade_plan) is Wo16TradePlanBinding,
            type(risk_observation) is Wo16RiskObservationBinding,
            type(timing_handoff) is Wo16TimingHandoffBinding,
            type(session) is Wo16SessionFactBinding,
        )
    ):
        _reject(Wo16BindingFailure.SOURCE_EVIDENCE_INVALID)
    if (
        risk_observation.trade_plan_identity != trade_plan.trade_plan_identity
        or risk_observation.trade_plan_integrity != trade_plan.trade_plan_integrity
        or timing_handoff.trade_plan_identity != trade_plan.trade_plan_identity
        or timing_handoff.trade_plan_integrity != trade_plan.trade_plan_integrity
    ):
        _reject(Wo16BindingFailure.CANONICAL_LINEAGE_MISMATCH)
    if (
        timing_handoff.session_identity != session.session_identity
        or timing_handoff.calendar_identity != session.calendar_identity
        or timing_handoff.calendar_version != session.calendar_version
    ):
        _reject(Wo16BindingFailure.WO15_SESSION_STALE)
    return create_wo16_upstream_lineage(
        trade_plan=trade_plan,
        risk_observation=risk_observation,
        timing_handoff=timing_handoff,
        session=session,
        provenance=provenance,
    )


def _validate_source(value: object, failure: Wo16BindingFailure) -> None:
    try:
        value.__post_init__()  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError) as error:
        raise Wo16BindingRejected(failure) from error


def _reject(failure: Wo16BindingFailure) -> None:
    raise Wo16BindingRejected(failure)


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_document_bytes(value)).hexdigest().upper()


__all__ = [
    "Wo16BindingFailure",
    "Wo16BindingRejected",
    "bind_wo16_risk_observation",
    "bind_wo16_session_fact",
    "bind_wo16_timing_handoff",
    "bind_wo16_trade_plan",
    "bind_wo16_upstream",
    "is_wo16_risk_state_admissible",
    "is_wo16_timing_state_eligible",
]
