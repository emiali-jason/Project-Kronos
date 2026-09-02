"""WO-15A immutable Entry-Timing contracts and exact WO-13 admission.

This module is deliberately contract-only.  It does not decide Pullback or
Breakout timing, calculate telemetry, persist state, compose runtime services,
or expose Browser, Sponsor, Risk-permission, execution, or broker authority.
"""

from __future__ import annotations

from collections.abc import Sequence
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
from kronos.intraday.probables_v2 import SemanticQualificationFactV2
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import CurrentWo13Pointer, Wo13TradePlan
from kronos.intraday.wo13_handoff import Wo13SetupFamily, Wo13Step31Handoff
from kronos.market.schedule import MarketDaySchedule, TradingDayStatus


WO15_CONTRACT_VERSION = "1.0.0"
WO15_CORE_IDENTITY = "KRONOS-INTRADAY-WO15-ENTRY-TIMING-V1"
WO15_AUTHORITY = "COMPLETED_5M_ENTRY_TIMING_QUALIFICATION_ONLY"
WO15_POLICY_IDENTITY = "KRONOS-INTRADAY-WO15-ENTRY-TIMING-POLICY-V1"
WO15_POLICY_VERSION = "1.0.0"
WO15_POLICY_CHECKSUM = (
    "d36386a98e2f1b78e5b70d0c27079c056951fd76a5b70ec2e9fa1bc1615a3f26"
)
WO15_WO13_HANDOFF_IDENTITY = "KRONOS-INTRADAY-WO15-WO13-HANDOFF-V1"
WO15_SESSION_BINDING_IDENTITY = "KRONOS-INTRADAY-WO15-SESSION-BINDING-V1"
WO15_FIVE_MINUTE_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-WO15-COMPLETED-5M-EVIDENCE-V1"
)
WO15_PROGRESSION_ADAPTER_IDENTITY = (
    "KRONOS-INTRADAY-WO15-PROGRESSION-ADAPTER-V1"
)
WO15_TIMING_CYCLE_IDENTITY = "KRONOS-INTRADAY-WO15-TIMING-CYCLE-V1"
WO15_TIMING_OBSERVATION_IDENTITY = (
    "KRONOS-INTRADAY-WO15-TIMING-OBSERVATION-V1"
)
WO15_TIMING_TRANSITION_IDENTITY = (
    "KRONOS-INTRADAY-WO15-TIMING-TRANSITION-V1"
)
WO15_CYCLE_EVALUATION_IDENTITY = (
    "KRONOS-INTRADAY-WO15-CYCLE-EVALUATION-V1"
)


class Wo15ContractError(ValueError):
    """Sanitized invalid-contract failure."""


class Wo15TimingState(StrEnum):
    TIMING_NOT_EVALUATED = "TIMING_NOT_EVALUATED"
    TIMING_WAITING = "TIMING_WAITING"
    TIMING_QUALIFIED = "TIMING_QUALIFIED"
    TIMING_FAILED = "TIMING_FAILED"
    TIMING_EXPIRED = "TIMING_EXPIRED"
    TIMING_UNAVAILABLE = "TIMING_UNAVAILABLE"


WO15_STATE_PRECEDENCE = (
    Wo15TimingState.TIMING_UNAVAILABLE,
    Wo15TimingState.TIMING_EXPIRED,
    Wo15TimingState.TIMING_FAILED,
    Wo15TimingState.TIMING_QUALIFIED,
    Wo15TimingState.TIMING_WAITING,
)


class Wo15QualificationPath(StrEnum):
    PULLBACK_CONTINUATION = "PULLBACK_CONTINUATION"
    DIRECT_ACCEPTANCE = "DIRECT_ACCEPTANCE"
    RETEST_RESUMPTION = "RETEST_RESUMPTION"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Wo15ProgressionSemantics(StrEnum):
    ALIGNED = "ALIGNED"
    NON_DIRECTIONAL_FORMING = "NON_DIRECTIONAL_FORMING"
    CONTRADICTORY = "CONTRADICTORY"
    UNAVAILABLE = "UNAVAILABLE"


class Wo15ExpiryCause(StrEnum):
    SESSION_END = "SESSION_END"
    WO13_PLAN_SUPERSEDED = "WO13_PLAN_SUPERSEDED"
    UPSTREAM_CYCLE_SUPERSEDED = "UPSTREAM_CYCLE_SUPERSEDED"
    INSTRUMENT_CONTRACT_SUPERSEDED = "INSTRUMENT_CONTRACT_SUPERSEDED"
    DOMAIN008_SESSION_INVALID = "DOMAIN_008_MARKET_SESSION_INVALID_OR_CLOSED"


class Wo15TrustFailure(StrEnum):
    WO13_PLAN_NOT_CURRENT = "WO13_PLAN_NOT_CURRENT"
    WO13_PLAN_SUPERSEDED = "WO13_PLAN_SUPERSEDED"
    WO13_INTEGRITY_INVALID = "WO13_INTEGRITY_INVALID"
    DIRECTION_MISMATCH = "DIRECTION_MISMATCH"
    SETUP_FAMILY_MISMATCH = "SETUP_FAMILY_MISMATCH"
    SUBJECT_MISMATCH = "SUBJECT_MISMATCH"
    MARKET_FAMILY_MISMATCH = "MARKET_FAMILY_MISMATCH"
    INSTRUMENT_MISMATCH = "INSTRUMENT_MISMATCH"
    ACTIVE_CONTRACT_MISMATCH = "ACTIVE_CONTRACT_MISMATCH"
    ROLL_LINEAGE_MISMATCH = "ROLL_LINEAGE_MISMATCH"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    POLICY_MISMATCH = "POLICY_MISMATCH"
    FIVE_MINUTE_EVIDENCE_STALE = "FIVE_MINUTE_EVIDENCE_STALE"
    FIVE_MINUTE_EVIDENCE_INCOMPLETE = "FIVE_MINUTE_EVIDENCE_INCOMPLETE"
    OBSERVATION_BOUNDARY_MISMATCH = "OBSERVATION_BOUNDARY_MISMATCH"
    SOURCE_EVIDENCE_INVALID = "SOURCE_EVIDENCE_INVALID"
    UPSTREAM_COMMISSIONING_UNAVAILABLE = "UPSTREAM_COMMISSIONING_UNAVAILABLE"


class Wo15SessionDisposition(StrEnum):
    VALID_TRADING_SESSION = "VALID_TRADING_SESSION"


class Wo15AdmissionRejected(Wo15ContractError):
    """Exact trust-boundary rejection with TIMING_UNAVAILABLE semantics."""

    def __init__(self, reason: Wo15TrustFailure) -> None:
        if type(reason) is not Wo15TrustFailure:
            raise Wo15ContractError("WO15_TRUST_FAILURE_INVALID")
        self.reason = reason
        self.timing_state = Wo15TimingState.TIMING_UNAVAILABLE
        super().__init__(reason.value)


@dataclass(frozen=True, slots=True)
class Wo15PolicyBinding:
    policy_identity: str = WO15_POLICY_IDENTITY
    policy_version: str = WO15_POLICY_VERSION
    policy_checksum: str = WO15_POLICY_CHECKSUM
    authority: str = WO15_AUTHORITY
    completed_five_minute_authority: bool = True
    sponsor_decision_authority: bool = False
    paper_authority: bool = False
    live_authority: bool = False
    ignore_authority: bool = False
    position_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        if (
            self.policy_identity != WO15_POLICY_IDENTITY
            or self.policy_version != WO15_POLICY_VERSION
            or self.policy_checksum != WO15_POLICY_CHECKSUM
            or self.authority != WO15_AUTHORITY
            or self.completed_five_minute_authority is not True
            or any((
                self.sponsor_decision_authority,
                self.paper_authority,
                self.live_authority,
                self.ignore_authority,
                self.position_authority,
                self.broker_authority,
            ))
        ):
            raise Wo15ContractError("WO15_POLICY_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo15SessionBinding:
    binding_identity: str
    binding_integrity: str
    exchange: str
    trading_date: date
    session_identity: str
    calendar_identity: str
    calendar_version: str
    windows: tuple[tuple[datetime, datetime], ...]
    session_opens_at: datetime
    session_closes_at: datetime
    disposition: Wo15SessionDisposition
    schema_identity: str = WO15_SESSION_BINDING_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "binding_identity", "binding_integrity")
        if (
            not _texts((
                self.exchange,
                self.session_identity,
                self.calendar_identity,
                self.calendar_version,
            ))
            or type(self.trading_date) is not date
            or not self.windows
            or any(
                len(window) != 2
                or not _aware(window[0])
                or not _aware(window[1])
                or window[0] >= window[1]
                for window in self.windows
            )
            or not _aware(self.session_opens_at)
            or not _aware(self.session_closes_at)
            or self.session_opens_at >= self.session_closes_at
            or type(self.disposition) is not Wo15SessionDisposition
            or self.disposition is not Wo15SessionDisposition.VALID_TRADING_SESSION
            or self.schema_identity != WO15_SESSION_BINDING_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.binding_identity != _identity("INTRADAY-WO15-SESSION-", values)
            or self.binding_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-SESSION-", values)
        ):
            raise Wo15ContractError("WO15_SESSION_BINDING_INVALID")


def bind_wo15_session(schedule: MarketDaySchedule) -> Wo15SessionBinding:
    if (
        type(schedule) is not MarketDaySchedule
        or schedule.status is not TradingDayStatus.TRADING
        or not schedule.windows
    ):
        raise Wo15AdmissionRejected(Wo15TrustFailure.SESSION_MISMATCH)
    values = {
        "exchange": schedule.exchange,
        "trading_date": schedule.trading_date,
        "session_identity": schedule.session_id,
        "calendar_identity": schedule.source_identity,
        "calendar_version": schedule.source_version,
        "windows": tuple((item.opens_at, item.closes_at) for item in schedule.windows),
        "session_opens_at": schedule.windows[0].opens_at,
        "session_closes_at": schedule.windows[-1].closes_at,
        "disposition": Wo15SessionDisposition.VALID_TRADING_SESSION,
        "schema_identity": WO15_SESSION_BINDING_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    return Wo15SessionBinding(
        binding_identity=_identity("INTRADAY-WO15-SESSION-", values),
        binding_integrity=_identity("INTEGRITY-INTRADAY-WO15-SESSION-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo15Wo13Handoff:
    handoff_identity: str
    handoff_integrity: str
    current_pointer_identity: str
    current_pointer_integrity: str
    wo13_trade_plan_identity: str
    wo13_trade_plan_integrity: str
    wo13_request_identity: str
    wo13_request_integrity: str
    wo13_handoff_identity: str
    wo13_handoff_integrity: str
    source_wo12_result_identity: str
    source_wo12_result_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    direction: SemanticDirection
    setup_family: Wo13SetupFamily
    entry_reference: Decimal
    analysis_boundary: datetime
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    stop: Decimal | None
    thesis_invalidation_reference: Decimal | None
    thesis_invalidation_event: str | None
    setup_native_target: Decimal | None
    canonical_target: Decimal | None
    risk_distance: Decimal | None
    reward_distance: Decimal | None
    model_rr: Decimal | None
    wo13_policy_identity: str
    wo13_policy_version: str
    wo13_policy_checksum: str
    source_evidence_identities: tuple[str, ...]
    source_evidence_integrities: tuple[str, ...]
    policy: Wo15PolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO15_WO13_HANDOFF_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION
    authority: str = WO15_AUTHORITY
    risk_prerequisite: bool = False
    sponsor_decision_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_reference", _decimal(self.entry_reference))
        for name in (
            "stop", "thesis_invalidation_reference", "setup_native_target",
            "canonical_target", "risk_distance", "reward_distance", "model_rr",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(value))
        values = _without(self, "handoff_identity", "handoff_integrity")
        mcx = self.market_family is IntradayMarketFamily.MCX
        if (
            not _texts((
                self.current_pointer_identity,
                self.current_pointer_integrity,
                self.wo13_trade_plan_identity,
                self.wo13_trade_plan_integrity,
                self.wo13_request_identity,
                self.wo13_request_integrity,
                self.wo13_handoff_identity,
                self.wo13_handoff_integrity,
                self.source_wo12_result_identity,
                self.source_wo12_result_integrity,
                self.canonical_subject_identity,
                self.instrument_identity,
                self.wo13_policy_identity,
                self.wo13_policy_version,
                self.wo13_policy_checksum,
                *self.provenance,
            ))
            or type(self.market_family) is not IntradayMarketFamily
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.setup_family) is not Wo13SetupFamily
            or not _aware(self.analysis_boundary)
            or not self.entry_reference.is_finite()
            or mcx != (self.actual_contract_identity is not None)
            or mcx != (self.roll_lineage_identity is not None)
            or len(self.source_evidence_identities) != len(self.source_evidence_integrities)
            or not _texts(self.source_evidence_identities)
            or not _texts(self.source_evidence_integrities)
            or type(self.policy) is not Wo15PolicyBinding
            or self.schema_identity != WO15_WO13_HANDOFF_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.authority != WO15_AUTHORITY
            or any((self.risk_prerequisite, self.sponsor_decision_authority,
                    self.execution_authority, self.broker_authority))
            or self.handoff_identity != _identity("INTRADAY-WO15-WO13-HANDOFF-", values)
            or self.handoff_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-WO13-HANDOFF-", values)
        ):
            raise Wo15ContractError("WO15_WO13_HANDOFF_INVALID")


def create_wo15_wo13_handoff(
    *,
    current_pointer: CurrentWo13Pointer,
    trade_plan: Wo13TradePlan,
    source_handoff: Wo13Step31Handoff,
    policy: Wo15PolicyBinding | None = None,
    provenance: tuple[str, ...] = ("ADR-0025",),
) -> Wo15Wo13Handoff:
    """Admit only the exact current immutable WO-13 plan."""

    actual_policy = policy or Wo15PolicyBinding()
    if type(current_pointer) is not CurrentWo13Pointer or type(trade_plan) is not Wo13TradePlan:
        raise Wo15AdmissionRejected(Wo15TrustFailure.WO13_PLAN_NOT_CURRENT)
    if type(source_handoff) is not Wo13Step31Handoff:
        raise Wo15AdmissionRejected(Wo15TrustFailure.SOURCE_EVIDENCE_INVALID)
    try:
        current_pointer.__post_init__()
        trade_plan.__post_init__()
        source_handoff.__post_init__()
    except (ValueError, TypeError) as error:
        raise Wo15AdmissionRejected(Wo15TrustFailure.WO13_INTEGRITY_INVALID) from error
    if type(actual_policy) is not Wo15PolicyBinding:
        raise Wo15AdmissionRejected(Wo15TrustFailure.POLICY_MISMATCH)
    pointer_pairs = (
        (current_pointer.trade_plan_identity, trade_plan.trade_plan_identity),
        (current_pointer.trade_plan_integrity, trade_plan.trade_plan_integrity),
        (current_pointer.request_identity, trade_plan.request_identity),
        (current_pointer.request_integrity, trade_plan.request_integrity),
        (current_pointer.handoff_identity, trade_plan.source_handoff_identity),
        (current_pointer.handoff_integrity, trade_plan.source_handoff_integrity),
        (current_pointer.source_wo12_result_identity, trade_plan.source_wo12_result_identity),
    )
    if any(left != right for left, right in pointer_pairs):
        raise Wo15AdmissionRejected(Wo15TrustFailure.WO13_PLAN_NOT_CURRENT)
    if (
        source_handoff.handoff_identity != trade_plan.source_handoff_identity
        or source_handoff.handoff_integrity != trade_plan.source_handoff_integrity
        or source_handoff.wo12_result_identity != trade_plan.source_wo12_result_identity
        or source_handoff.wo12_result_integrity != trade_plan.source_wo12_result_integrity
    ):
        raise Wo15AdmissionRejected(Wo15TrustFailure.SOURCE_EVIDENCE_INVALID)
    for left, right, failure in (
        (current_pointer.canonical_subject_identity, trade_plan.canonical_subject_identity,
         Wo15TrustFailure.SUBJECT_MISMATCH),
        (source_handoff.canonical_subject_identity, trade_plan.canonical_subject_identity,
         Wo15TrustFailure.SUBJECT_MISMATCH),
        (current_pointer.market_family, trade_plan.market_family,
         Wo15TrustFailure.MARKET_FAMILY_MISMATCH),
        (source_handoff.market_family, trade_plan.market_family,
         Wo15TrustFailure.MARKET_FAMILY_MISMATCH),
        (current_pointer.direction, trade_plan.direction,
         Wo15TrustFailure.DIRECTION_MISMATCH),
        (source_handoff.inherited_direction, trade_plan.direction,
         Wo15TrustFailure.DIRECTION_MISMATCH),
        (current_pointer.setup_family, trade_plan.setup_family,
         Wo15TrustFailure.SETUP_FAMILY_MISMATCH),
        (source_handoff.setup_family, trade_plan.setup_family,
         Wo15TrustFailure.SETUP_FAMILY_MISMATCH),
        (source_handoff.instrument_identity, trade_plan.instrument_identity,
         Wo15TrustFailure.INSTRUMENT_MISMATCH),
        (source_handoff.actual_contract_identity, trade_plan.actual_contract_identity,
         Wo15TrustFailure.ACTIVE_CONTRACT_MISMATCH),
    ):
        if left != right:
            raise Wo15AdmissionRejected(failure)
    if trade_plan.entry_reference is None:
        raise Wo15AdmissionRejected(Wo15TrustFailure.SOURCE_EVIDENCE_INVALID)
    if (
        trade_plan.market_family is IntradayMarketFamily.MCX
        and (
            source_handoff.roll_lineage_identity is None
            or getattr(source_handoff.commissioning_state, "value", None) != "COMMISSIONED"
        )
    ):
        raise Wo15AdmissionRejected(Wo15TrustFailure.UPSTREAM_COMMISSIONING_UNAVAILABLE)
    values = {
        "current_pointer_identity": current_pointer.pointer_identity,
        "current_pointer_integrity": current_pointer.pointer_integrity,
        "wo13_trade_plan_identity": trade_plan.trade_plan_identity,
        "wo13_trade_plan_integrity": trade_plan.trade_plan_integrity,
        "wo13_request_identity": trade_plan.request_identity,
        "wo13_request_integrity": trade_plan.request_integrity,
        "wo13_handoff_identity": trade_plan.source_handoff_identity,
        "wo13_handoff_integrity": trade_plan.source_handoff_integrity,
        "source_wo12_result_identity": trade_plan.source_wo12_result_identity,
        "source_wo12_result_integrity": trade_plan.source_wo12_result_integrity,
        "canonical_subject_identity": trade_plan.canonical_subject_identity,
        "market_family": trade_plan.market_family,
        "direction": trade_plan.direction,
        "setup_family": trade_plan.setup_family,
        "entry_reference": trade_plan.entry_reference,
        "analysis_boundary": trade_plan.analysis_boundary,
        "instrument_identity": trade_plan.instrument_identity,
        "actual_contract_identity": trade_plan.actual_contract_identity,
        "roll_lineage_identity": source_handoff.roll_lineage_identity,
        "stop": trade_plan.stop,
        "thesis_invalidation_reference": trade_plan.thesis_invalidation_reference,
        "thesis_invalidation_event": trade_plan.thesis_invalidation_event,
        "setup_native_target": trade_plan.setup_native_target,
        "canonical_target": trade_plan.canonical_target,
        "risk_distance": trade_plan.risk_distance,
        "reward_distance": trade_plan.reward_distance,
        "model_rr": trade_plan.model_rr,
        "wo13_policy_identity": trade_plan.policy.policy_identity,
        "wo13_policy_version": trade_plan.policy.policy_version,
        "wo13_policy_checksum": trade_plan.policy.policy_checksum,
        "source_evidence_identities": trade_plan.source_evidence_identities,
        "source_evidence_integrities": trade_plan.source_evidence_integrities,
        "policy": actual_policy,
        "provenance": provenance,
        "schema_identity": WO15_WO13_HANDOFF_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
        "authority": WO15_AUTHORITY,
        "risk_prerequisite": False,
        "sponsor_decision_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo15Wo13Handoff(
        handoff_identity=_identity("INTRADAY-WO15-WO13-HANDOFF-", values),
        handoff_integrity=_identity("INTEGRITY-INTRADAY-WO15-WO13-HANDOFF-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo15FiveMinuteEvidence:
    evidence_identity: str
    evidence_integrity: str
    source_candle_identity: str
    source_candle_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    exchange: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    trading_date: date
    candle_start: datetime
    candle_end: datetime
    observation_boundary: datetime
    completion: str
    timeframe: str
    schema_identity: str = WO15_FIVE_MINUTE_EVIDENCE_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "evidence_identity", "evidence_integrity")
        mcx = self.market_family is IntradayMarketFamily.MCX
        if (
            not _texts((self.source_candle_identity, self.source_candle_integrity,
                        self.canonical_subject_identity, self.exchange,
                        self.instrument_identity, self.session_identity))
            or type(self.market_family) is not IntradayMarketFamily
            or type(self.trading_date) is not date
            or not all(_aware(item) for item in (
                self.candle_start, self.candle_end, self.observation_boundary
            ))
            or self.candle_start >= self.candle_end
            or (self.candle_end - self.candle_start).total_seconds() != 300
            or self.candle_end > self.observation_boundary
            or self.completion != "COMPLETE"
            or self.timeframe != "5M"
            or mcx != (self.actual_contract_identity is not None)
            or mcx != (self.roll_lineage_identity is not None)
            or mcx and self.exchange != "MCX"
            or self.schema_identity != WO15_FIVE_MINUTE_EVIDENCE_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.evidence_identity != _identity("INTRADAY-WO15-5M-EVIDENCE-", values)
            or self.evidence_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-5M-EVIDENCE-", values)
        ):
            raise Wo15ContractError("WO15_COMPLETED_5M_EVIDENCE_INVALID")


def bind_completed_five_minute_evidence(
    *,
    source: GovernedHistoricalCandlePayload,
    market_family: IntradayMarketFamily,
    instrument_identity: str,
    actual_contract_identity: str | None = None,
    roll_lineage_identity: str | None = None,
) -> Wo15FiveMinuteEvidence:
    if type(source) is not GovernedHistoricalCandlePayload:
        raise Wo15AdmissionRejected(Wo15TrustFailure.FIVE_MINUTE_EVIDENCE_INCOMPLETE)
    try:
        source.__post_init__()
    except (ValueError, TypeError) as error:
        raise Wo15AdmissionRejected(Wo15TrustFailure.SOURCE_EVIDENCE_INVALID) from error
    if source.timeframe.value != "5M" or source.completion_state != "COMPLETE":
        raise Wo15AdmissionRejected(Wo15TrustFailure.FIVE_MINUTE_EVIDENCE_INCOMPLETE)
    values = {
        "source_candle_identity": source.candle_identity,
        "source_candle_integrity": source.integrity_identity,
        "canonical_subject_identity": source.canonical_subject_identity,
        "market_family": market_family,
        "exchange": source.exchange,
        "instrument_identity": instrument_identity,
        "actual_contract_identity": actual_contract_identity,
        "roll_lineage_identity": roll_lineage_identity,
        "session_identity": source.market_session_identity,
        "trading_date": source.candle_end.date(),
        "candle_start": source.candle_start,
        "candle_end": source.candle_end,
        "observation_boundary": source.observation_boundary,
        "completion": source.completion_state,
        "timeframe": source.timeframe.value,
        "schema_identity": WO15_FIVE_MINUTE_EVIDENCE_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    try:
        return Wo15FiveMinuteEvidence(
            evidence_identity=_identity("INTRADAY-WO15-5M-EVIDENCE-", values),
            evidence_integrity=_identity("INTEGRITY-INTRADAY-WO15-5M-EVIDENCE-", values),
            **values,
        )
    except Wo15ContractError as error:
        raise Wo15AdmissionRejected(Wo15TrustFailure.FIVE_MINUTE_EVIDENCE_INCOMPLETE) from error


@dataclass(frozen=True, slots=True)
class Wo15ProgressionEvidence:
    adapter_identity: str
    adapter_integrity: str
    source_fact_identity: str
    source_fact_integrity: str
    canonical_subject_identity: str
    analysis_boundary: datetime
    inherited_direction: SemanticDirection
    source_direction: SemanticDirection
    semantics: Wo15ProgressionSemantics
    schema_identity: str = WO15_PROGRESSION_ADAPTER_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION
    algorithm_authority: str = "NONE"

    def __post_init__(self) -> None:
        values = _without(self, "adapter_identity", "adapter_integrity")
        if (
            not _texts((self.source_fact_identity, self.source_fact_integrity,
                        self.canonical_subject_identity))
            or not _aware(self.analysis_boundary)
            or self.inherited_direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.source_direction) is not SemanticDirection
            or type(self.semantics) is not Wo15ProgressionSemantics
            or self.schema_identity != WO15_PROGRESSION_ADAPTER_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.algorithm_authority != "NONE"
            or self.adapter_identity != _identity("INTRADAY-WO15-PROGRESSION-", values)
            or self.adapter_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-PROGRESSION-", values)
        ):
            raise Wo15ContractError("WO15_PROGRESSION_ADAPTER_INVALID")


def adapt_five_minute_progression(
    fact: SemanticQualificationFactV2,
    *,
    inherited_direction: SemanticDirection,
) -> Wo15ProgressionEvidence:
    """Map an existing governed semantic fact; calculate no price semantics."""

    if type(fact) is not SemanticQualificationFactV2 or fact.family != "5M_PROGRESSION":
        raise Wo15AdmissionRejected(Wo15TrustFailure.SOURCE_EVIDENCE_INVALID)
    try:
        fact.__post_init__()
    except (ValueError, TypeError) as error:
        raise Wo15AdmissionRejected(Wo15TrustFailure.SOURCE_EVIDENCE_INVALID) from error
    if inherited_direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}:
        raise Wo15AdmissionRejected(Wo15TrustFailure.DIRECTION_MISMATCH)
    if fact.availability == "UNAVAILABLE" or fact.direction is SemanticDirection.UNAVAILABLE:
        semantics = Wo15ProgressionSemantics.UNAVAILABLE
    elif fact.direction is inherited_direction:
        semantics = Wo15ProgressionSemantics.ALIGNED
    elif fact.direction is SemanticDirection.NON_DIRECTIONAL:
        semantics = Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING
    else:
        semantics = Wo15ProgressionSemantics.CONTRADICTORY
    values = {
        "source_fact_identity": fact.fact_identity,
        "source_fact_integrity": fact.integrity_identity,
        "canonical_subject_identity": fact.canonical_subject_identity,
        "analysis_boundary": fact.analysis_boundary,
        "inherited_direction": inherited_direction,
        "source_direction": fact.direction,
        "semantics": semantics,
        "schema_identity": WO15_PROGRESSION_ADAPTER_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
        "algorithm_authority": "NONE",
    }
    return Wo15ProgressionEvidence(
        adapter_identity=_identity("INTRADAY-WO15-PROGRESSION-", values),
        adapter_integrity=_identity("INTEGRITY-INTRADAY-WO15-PROGRESSION-", values),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo15TimingCycle:
    timing_cycle_id: str
    timing_cycle_integrity: str
    wo13_trade_plan_identity: str
    wo13_trade_plan_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    direction: SemanticDirection
    setup_family: Wo13SetupFamily
    entry_reference: Decimal
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    session_identity: str
    calendar_identity: str
    calendar_version: str
    policy: Wo15PolicyBinding
    cycle_creation_boundary: datetime
    cycle_created_at: datetime
    cycle_ordinal: int
    predecessor_cycle_identity: str | None
    successor_reset_reference: str | None
    schema_identity: str = WO15_TIMING_CYCLE_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_reference", _decimal(self.entry_reference))
        values = _without(self, "timing_cycle_id", "timing_cycle_integrity")
        first = self.cycle_ordinal == 1
        if (
            not _texts((self.wo13_trade_plan_identity, self.wo13_trade_plan_integrity,
                        self.canonical_subject_identity, self.instrument_identity,
                        self.session_identity, self.calendar_identity,
                        self.calendar_version))
            or type(self.market_family) is not IntradayMarketFamily
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.setup_family) is not Wo13SetupFamily
            or not self.entry_reference.is_finite()
            or not _aware(self.cycle_creation_boundary)
            or not _aware(self.cycle_created_at)
            or self.cycle_created_at < self.cycle_creation_boundary
            or type(self.cycle_ordinal) is not int or self.cycle_ordinal < 1
            or first != (self.predecessor_cycle_identity is None)
            or first != (self.successor_reset_reference is None)
            or not first and not _texts((self.predecessor_cycle_identity,
                                         self.successor_reset_reference))
            or type(self.policy) is not Wo15PolicyBinding
            or self.schema_identity != WO15_TIMING_CYCLE_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.timing_cycle_id != _identity("INTRADAY-WO15-TIMING-CYCLE-", values)
            or self.timing_cycle_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-TIMING-CYCLE-", values)
        ):
            raise Wo15ContractError("WO15_TIMING_CYCLE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo15TimingTransition:
    transition_identity: str
    transition_integrity: str
    timing_cycle_id: str
    wo13_trade_plan_identity: str
    prior_state: Wo15TimingState
    current_state: Wo15TimingState
    cause: str
    observation_boundary: datetime
    completed_five_minute_evidence_identity: str
    expiry_cause: Wo15ExpiryCause | None
    trust_failure: Wo15TrustFailure | None
    transitioned_at: datetime
    policy: Wo15PolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO15_TIMING_TRANSITION_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "transition_identity", "transition_integrity")
        if (
            not _texts((self.timing_cycle_id, self.wo13_trade_plan_identity,
                        self.cause, self.completed_five_minute_evidence_identity,
                        *self.provenance))
            or type(self.prior_state) is not Wo15TimingState
            or type(self.current_state) is not Wo15TimingState
            or not _valid_transition(self.prior_state, self.current_state)
            or not _aware(self.observation_boundary)
            or not _aware(self.transitioned_at)
            or self.transitioned_at < self.observation_boundary
            or (self.current_state is Wo15TimingState.TIMING_EXPIRED)
            != (self.expiry_cause is not None)
            or (self.current_state is Wo15TimingState.TIMING_UNAVAILABLE)
            != (self.trust_failure is not None)
            or type(self.policy) is not Wo15PolicyBinding
            or self.schema_identity != WO15_TIMING_TRANSITION_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.transition_identity != _identity("INTRADAY-WO15-TRANSITION-", values)
            or self.transition_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-TRANSITION-", values)
        ):
            raise Wo15ContractError("WO15_TIMING_TRANSITION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo15TimingObservation:
    observation_identity: str
    observation_integrity: str
    timing_cycle_id: str
    transition_identity: str
    prior_state: Wo15TimingState
    current_state: Wo15TimingState
    observation_boundary: datetime
    completed_five_minute_evidence_identity: str
    completed_five_minute_evidence_integrity: str
    progression_evidence_identity: str
    progression_evidence_integrity: str
    transition_cause: str
    qualification_path: Wo15QualificationPath
    observed_at: datetime
    telemetry_references: tuple[str, ...]
    policy: Wo15PolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO15_TIMING_OBSERVATION_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "observation_identity", "observation_integrity")
        if (
            not _texts((self.timing_cycle_id, self.transition_identity,
                        self.completed_five_minute_evidence_identity,
                        self.completed_five_minute_evidence_integrity,
                        self.progression_evidence_identity,
                        self.progression_evidence_integrity,
                        self.transition_cause, *self.provenance))
            or type(self.prior_state) is not Wo15TimingState
            or type(self.current_state) is not Wo15TimingState
            or not _valid_transition(self.prior_state, self.current_state)
            or not _aware(self.observation_boundary)
            or not _aware(self.observed_at)
            or self.observed_at < self.observation_boundary
            or type(self.qualification_path) is not Wo15QualificationPath
            or not _optional_texts(self.telemetry_references)
            or type(self.policy) is not Wo15PolicyBinding
            or self.schema_identity != WO15_TIMING_OBSERVATION_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.observation_identity != _identity("INTRADAY-WO15-OBSERVATION-", values)
            or self.observation_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-OBSERVATION-", values)
        ):
            raise Wo15ContractError("WO15_TIMING_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class Wo15CycleEvaluation:
    evaluation_identity: str
    evaluation_integrity: str
    cycle: Wo15TimingCycle
    observation: Wo15TimingObservation
    transition: Wo15TimingTransition
    schema_identity: str = WO15_CYCLE_EVALUATION_IDENTITY
    schema_version: str = WO15_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "evaluation_identity", "evaluation_integrity")
        if (
            type(self.cycle) is not Wo15TimingCycle
            or type(self.observation) is not Wo15TimingObservation
            or type(self.transition) is not Wo15TimingTransition
            or self.observation.timing_cycle_id != self.cycle.timing_cycle_id
            or self.transition.timing_cycle_id != self.cycle.timing_cycle_id
            or self.observation.transition_identity != self.transition.transition_identity
            or self.observation.prior_state is not self.transition.prior_state
            or self.observation.current_state is not self.transition.current_state
            or self.observation.observation_boundary != self.transition.observation_boundary
            or self.schema_identity != WO15_CYCLE_EVALUATION_IDENTITY
            or self.schema_version != WO15_CONTRACT_VERSION
            or self.evaluation_identity != _identity("INTRADAY-WO15-EVALUATION-", values)
            or self.evaluation_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-EVALUATION-", values)
        ):
            raise Wo15ContractError("WO15_CYCLE_EVALUATION_INVALID")


def timing_state_before_first_evaluation(
    admission: Wo15Wo13Handoff,
) -> tuple[Wo15TimingState, None]:
    if type(admission) is not Wo15Wo13Handoff:
        raise Wo15ContractError("WO15_PRE_CYCLE_INPUT_INVALID")
    admission.__post_init__()
    return Wo15TimingState.TIMING_NOT_EVALUATED, None


def create_first_cycle_evaluation(
    *,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
    current_state: Wo15TimingState,
    transition_cause: str,
    qualification_path: Wo15QualificationPath,
    cycle_created_at: datetime,
    observed_at: datetime,
    telemetry_references: tuple[str, ...] = (),
    expiry_cause: Wo15ExpiryCause | None = None,
    trust_failure: Wo15TrustFailure | None = None,
    provenance: tuple[str, ...] = ("ADR-0025", "WO-15A"),
) -> Wo15CycleEvaluation:
    if current_state not in {
        Wo15TimingState.TIMING_WAITING,
        Wo15TimingState.TIMING_QUALIFIED,
        Wo15TimingState.TIMING_FAILED,
        Wo15TimingState.TIMING_UNAVAILABLE,
    }:
        raise Wo15ContractError("WO15_FIRST_STATE_INVALID")
    _validate_evaluation_inputs(admission, session, evidence, progression)
    return _create_evaluation(
        admission=admission, session=session, evidence=evidence,
        progression=progression, prior_state=Wo15TimingState.TIMING_NOT_EVALUATED,
        current_state=current_state, transition_cause=transition_cause,
        qualification_path=qualification_path, cycle_created_at=cycle_created_at,
        observed_at=observed_at, cycle_ordinal=1, predecessor_cycle_identity=None,
        successor_reset_reference=None, telemetry_references=telemetry_references,
        expiry_cause=expiry_cause, trust_failure=trust_failure,
        provenance=provenance,
    )


def create_successor_cycle_evaluation(
    *,
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    predecessor: Wo15CycleEvaluation,
    reset_evidence_identity: str,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
    current_state: Wo15TimingState,
    transition_cause: str,
    qualification_path: Wo15QualificationPath,
    cycle_created_at: datetime,
    observed_at: datetime,
    telemetry_references: tuple[str, ...] = (),
    trust_failure: Wo15TrustFailure | None = None,
    provenance: tuple[str, ...] = ("ADR-0025", "WO-15A-SUCCESSOR-FOUNDATION"),
) -> Wo15CycleEvaluation:
    if (
        type(predecessor) is not Wo15CycleEvaluation
        or predecessor.transition.current_state is not Wo15TimingState.TIMING_FAILED
        or predecessor.cycle.wo13_trade_plan_identity != admission.wo13_trade_plan_identity
        or predecessor.cycle.session_identity != session.session_identity
        or evidence.candle_end <= predecessor.observation.observation_boundary
        or not _text(reset_evidence_identity)
        or current_state not in {
            Wo15TimingState.TIMING_WAITING,
            Wo15TimingState.TIMING_QUALIFIED,
            Wo15TimingState.TIMING_FAILED,
            Wo15TimingState.TIMING_UNAVAILABLE,
        }
    ):
        raise Wo15ContractError("WO15_SUCCESSOR_CYCLE_INVALID")
    _validate_evaluation_inputs(admission, session, evidence, progression)
    return _create_evaluation(
        admission=admission, session=session, evidence=evidence,
        progression=progression, prior_state=Wo15TimingState.TIMING_NOT_EVALUATED,
        current_state=current_state, transition_cause=transition_cause,
        qualification_path=qualification_path, cycle_created_at=cycle_created_at,
        observed_at=observed_at,
        cycle_ordinal=predecessor.cycle.cycle_ordinal + 1,
        predecessor_cycle_identity=predecessor.cycle.timing_cycle_id,
        successor_reset_reference=reset_evidence_identity,
        telemetry_references=telemetry_references, expiry_cause=None,
        trust_failure=trust_failure, provenance=provenance,
    )


def create_followup_observation(
    *,
    cycle: Wo15TimingCycle,
    prior_state: Wo15TimingState,
    current_state: Wo15TimingState,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
    transition_cause: str,
    qualification_path: Wo15QualificationPath,
    observed_at: datetime,
    telemetry_references: tuple[str, ...] = (),
    expiry_cause: Wo15ExpiryCause | None = None,
    trust_failure: Wo15TrustFailure | None = None,
    provenance: tuple[str, ...] = ("ADR-0025", "WO-15A"),
) -> tuple[Wo15TimingObservation, Wo15TimingTransition]:
    if type(cycle) is not Wo15TimingCycle:
        raise Wo15ContractError("WO15_FOLLOWUP_CYCLE_INVALID")
    if (
        evidence.canonical_subject_identity != cycle.canonical_subject_identity
        or evidence.instrument_identity != cycle.instrument_identity
        or evidence.actual_contract_identity != cycle.actual_contract_identity
        or evidence.roll_lineage_identity != cycle.roll_lineage_identity
        or evidence.session_identity != cycle.session_identity
        or evidence.candle_end <= cycle.cycle_creation_boundary
        or progression.canonical_subject_identity != cycle.canonical_subject_identity
        or progression.inherited_direction is not cycle.direction
    ):
        raise Wo15AdmissionRejected(Wo15TrustFailure.SOURCE_EVIDENCE_INVALID)
    return _observation_transition(
        cycle=cycle, evidence=evidence, progression=progression,
        prior_state=prior_state, current_state=current_state,
        transition_cause=transition_cause, qualification_path=qualification_path,
        observed_at=observed_at, telemetry_references=telemetry_references,
        expiry_cause=expiry_cause, trust_failure=trust_failure,
        provenance=provenance,
    )


def bind_cycle_evaluation(
    *,
    cycle: Wo15TimingCycle,
    observation: Wo15TimingObservation,
    transition: Wo15TimingTransition,
) -> Wo15CycleEvaluation:
    """Bind an existing append-only cycle observation and transition exactly."""

    values = {
        "cycle": cycle,
        "observation": observation,
        "transition": transition,
        "schema_identity": WO15_CYCLE_EVALUATION_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    return Wo15CycleEvaluation(
        evaluation_identity=_identity("INTRADAY-WO15-EVALUATION-", values),
        evaluation_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-EVALUATION-", values
        ),
        **values,
    )


def validate_one_active_cycle(
    cycle_states: Sequence[tuple[Wo15TimingCycle, Wo15TimingState]],
) -> None:
    terminal = {
        Wo15TimingState.TIMING_FAILED,
        Wo15TimingState.TIMING_EXPIRED,
        Wo15TimingState.TIMING_UNAVAILABLE,
    }
    active: set[str] = set()
    for cycle, state in cycle_states:
        if type(cycle) is not Wo15TimingCycle or type(state) is not Wo15TimingState:
            raise Wo15ContractError("WO15_ACTIVE_CYCLE_INPUT_INVALID")
        if state not in terminal and cycle.wo13_trade_plan_identity in active:
            raise Wo15ContractError("WO15_MULTIPLE_ACTIVE_CYCLES")
        if state not in terminal:
            active.add(cycle.wo13_trade_plan_identity)


def _validate_evaluation_inputs(
    admission: Wo15Wo13Handoff,
    session: Wo15SessionBinding,
    evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence,
) -> None:
    try:
        admission.__post_init__()
        session.__post_init__()
        evidence.__post_init__()
        progression.__post_init__()
    except (ValueError, TypeError) as error:
        raise Wo15AdmissionRejected(Wo15TrustFailure.SOURCE_EVIDENCE_INVALID) from error
    for value, expected, failure in (
        (evidence.canonical_subject_identity, admission.canonical_subject_identity,
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
        (evidence.trading_date, session.trading_date,
         Wo15TrustFailure.SESSION_MISMATCH),
        (progression.canonical_subject_identity, admission.canonical_subject_identity,
         Wo15TrustFailure.SUBJECT_MISMATCH),
        (progression.inherited_direction, admission.direction,
         Wo15TrustFailure.DIRECTION_MISMATCH),
    ):
        if value != expected:
            raise Wo15AdmissionRejected(failure)
    if evidence.candle_end <= admission.analysis_boundary:
        raise Wo15AdmissionRejected(Wo15TrustFailure.FIVE_MINUTE_EVIDENCE_STALE)
    expected_exchange = (
        "MCX" if admission.market_family is IntradayMarketFamily.MCX else "NSE"
    )
    if evidence.exchange != expected_exchange or session.exchange != expected_exchange:
        raise Wo15AdmissionRejected(Wo15TrustFailure.INSTRUMENT_MISMATCH)
    if (
        not any(
            opens_at <= evidence.candle_start
            and evidence.candle_end <= closes_at
            for opens_at, closes_at in session.windows
        )
        or progression.analysis_boundary != evidence.observation_boundary
    ):
        raise Wo15AdmissionRejected(Wo15TrustFailure.OBSERVATION_BOUNDARY_MISMATCH)


def _create_evaluation(
    *, admission: Wo15Wo13Handoff, session: Wo15SessionBinding,
    evidence: Wo15FiveMinuteEvidence, progression: Wo15ProgressionEvidence,
    prior_state: Wo15TimingState, current_state: Wo15TimingState,
    transition_cause: str, qualification_path: Wo15QualificationPath,
    cycle_created_at: datetime, observed_at: datetime, cycle_ordinal: int,
    predecessor_cycle_identity: str | None, successor_reset_reference: str | None,
    telemetry_references: tuple[str, ...], expiry_cause: Wo15ExpiryCause | None,
    trust_failure: Wo15TrustFailure | None, provenance: tuple[str, ...],
) -> Wo15CycleEvaluation:
    cycle_values = {
        "wo13_trade_plan_identity": admission.wo13_trade_plan_identity,
        "wo13_trade_plan_integrity": admission.wo13_trade_plan_integrity,
        "canonical_subject_identity": admission.canonical_subject_identity,
        "market_family": admission.market_family,
        "direction": admission.direction,
        "setup_family": admission.setup_family,
        "entry_reference": admission.entry_reference,
        "instrument_identity": admission.instrument_identity,
        "actual_contract_identity": admission.actual_contract_identity,
        "roll_lineage_identity": admission.roll_lineage_identity,
        "session_identity": session.session_identity,
        "calendar_identity": session.calendar_identity,
        "calendar_version": session.calendar_version,
        "policy": admission.policy,
        "cycle_creation_boundary": evidence.candle_end,
        "cycle_created_at": cycle_created_at,
        "cycle_ordinal": cycle_ordinal,
        "predecessor_cycle_identity": predecessor_cycle_identity,
        "successor_reset_reference": successor_reset_reference,
        "schema_identity": WO15_TIMING_CYCLE_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    cycle = Wo15TimingCycle(
        timing_cycle_id=_identity("INTRADAY-WO15-TIMING-CYCLE-", cycle_values),
        timing_cycle_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-TIMING-CYCLE-", cycle_values
        ),
        **cycle_values,
    )
    observation, transition = _observation_transition(
        cycle=cycle, evidence=evidence, progression=progression,
        prior_state=prior_state, current_state=current_state,
        transition_cause=transition_cause, qualification_path=qualification_path,
        observed_at=observed_at, telemetry_references=telemetry_references,
        expiry_cause=expiry_cause, trust_failure=trust_failure,
        provenance=provenance,
    )
    return bind_cycle_evaluation(
        cycle=cycle,
        observation=observation,
        transition=transition,
    )


def _observation_transition(
    *, cycle: Wo15TimingCycle, evidence: Wo15FiveMinuteEvidence,
    progression: Wo15ProgressionEvidence, prior_state: Wo15TimingState,
    current_state: Wo15TimingState, transition_cause: str,
    qualification_path: Wo15QualificationPath, observed_at: datetime,
    telemetry_references: tuple[str, ...], expiry_cause: Wo15ExpiryCause | None,
    trust_failure: Wo15TrustFailure | None, provenance: tuple[str, ...],
) -> tuple[Wo15TimingObservation, Wo15TimingTransition]:
    transition_values = {
        "timing_cycle_id": cycle.timing_cycle_id,
        "wo13_trade_plan_identity": cycle.wo13_trade_plan_identity,
        "prior_state": prior_state,
        "current_state": current_state,
        "cause": transition_cause,
        "observation_boundary": evidence.candle_end,
        "completed_five_minute_evidence_identity": evidence.evidence_identity,
        "expiry_cause": expiry_cause,
        "trust_failure": trust_failure,
        "transitioned_at": observed_at,
        "policy": cycle.policy,
        "provenance": provenance,
        "schema_identity": WO15_TIMING_TRANSITION_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    transition = Wo15TimingTransition(
        transition_identity=_identity("INTRADAY-WO15-TRANSITION-", transition_values),
        transition_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-TRANSITION-", transition_values
        ),
        **transition_values,
    )
    observation_values = {
        "timing_cycle_id": cycle.timing_cycle_id,
        "transition_identity": transition.transition_identity,
        "prior_state": prior_state,
        "current_state": current_state,
        "observation_boundary": evidence.candle_end,
        "completed_five_minute_evidence_identity": evidence.evidence_identity,
        "completed_five_minute_evidence_integrity": evidence.evidence_integrity,
        "progression_evidence_identity": progression.adapter_identity,
        "progression_evidence_integrity": progression.adapter_integrity,
        "transition_cause": transition_cause,
        "qualification_path": qualification_path,
        "observed_at": observed_at,
        "telemetry_references": telemetry_references,
        "policy": cycle.policy,
        "provenance": provenance,
        "schema_identity": WO15_TIMING_OBSERVATION_IDENTITY,
        "schema_version": WO15_CONTRACT_VERSION,
    }
    observation = Wo15TimingObservation(
        observation_identity=_identity("INTRADAY-WO15-OBSERVATION-", observation_values),
        observation_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-OBSERVATION-", observation_values
        ),
        **observation_values,
    )
    return observation, transition


def _valid_transition(prior: Wo15TimingState, current: Wo15TimingState) -> bool:
    allowed = {
        Wo15TimingState.TIMING_NOT_EVALUATED: {
            Wo15TimingState.TIMING_WAITING,
            Wo15TimingState.TIMING_QUALIFIED,
            Wo15TimingState.TIMING_FAILED,
            Wo15TimingState.TIMING_UNAVAILABLE,
        },
        Wo15TimingState.TIMING_WAITING: {
            Wo15TimingState.TIMING_WAITING,
            Wo15TimingState.TIMING_QUALIFIED,
            Wo15TimingState.TIMING_FAILED,
            Wo15TimingState.TIMING_EXPIRED,
            Wo15TimingState.TIMING_UNAVAILABLE,
        },
        Wo15TimingState.TIMING_QUALIFIED: {
            Wo15TimingState.TIMING_FAILED,
            Wo15TimingState.TIMING_EXPIRED,
        },
    }
    return current in allowed.get(prior, set())


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
        raise Wo15ContractError("WO15_DECIMAL_INVALID") from error
    if not result.is_finite():
        raise Wo15ContractError("WO15_DECIMAL_INVALID")
    return result


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(value) for value in values)


def _optional_texts(values: Sequence[object]) -> bool:
    return all(_text(value) for value in values)
