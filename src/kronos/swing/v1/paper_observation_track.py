"""Non-position PAPER market-path evidence governed by ADR-0016.

This module owns immutable research evidence only.  It creates no Sponsor
Position, objective model, Risk permission, fill, P&L, actual R, order, or
broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import RLock
from typing import Callable

from kronos.common.validated_reuse import ValidatedBytesReuse

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorActivationDisposition,
    SponsorObservationDecisionResult,
)
from kronos.swing.v1.step31_observation import (
    STEP31_OBSERVATION_CONTRACT_ID,
    STEP31_OBSERVATION_CONTRACT_ID_V1,
    STEP31_OBSERVATION_CONTRACT_VERSION,
    STEP31_OBSERVATION_CONTRACT_VERSION_V1,
    STEP31_OBSERVATION_POLICY_ID,
    STEP31_OBSERVATION_POLICY_VERSION,
    Step31WarningSeverity,
)


PAPER_OBSERVATION_TRACK_CONTRACT_ID = "KRONOS-SWING-PAPER-OBSERVATION-TRACK-V1"
PAPER_OBSERVATION_TRACK_CONTRACT_VERSION = "1"
PAPER_OBSERVATION_TRACK_POLICY_ID = "SWING-PAPER-OBSERVATION-TRACK-V1"
PAPER_OBSERVATION_TRACK_POLICY_VERSION = "1"
PAPER_OBSERVATION_TRACK_STORE_SCHEMA = "KRONOS-SWING-PAPER-OBSERVATION-STORE-V1"
PAPER_OBSERVATION_TRACK_AUTHORITY = (
    "NON_POSITION_RESEARCH_EVIDENCE_ONLY_NO_RISK_POSITION_OBJECTIVE_EXECUTION_"
    "OR_BROKER_AUTHORITY"
)
PAPER_OBSERVATION_MONITORING_APPLICABILITY_CONTRACT_ID = (
    "KRONOS-SWING-PAPER-OBSERVATION-MONITORING-APPLICABILITY-V1"
)
PAPER_OBSERVATION_MONITORING_APPLICABILITY_CONTRACT_VERSION = "1"
COMPACT_SCHEMA = "KRONOS-PAPER-OBSERVATION-COMPACT-V1"
COMPACT_POLICY = "LATEST-OBSERVATION-BOUNDED-REPLAY-V1"
COMPACT_TRANSITIONS = frozenset({
    "MONITORING_OPENED", "ENTRY_OBSERVED", "STOP_LEVEL_TOUCHED",
    "TARGET_LEVEL_TOUCHED", "BOTH_ORDERING_UNRESOLVED",
    "GAP_BEGAN", "GAP_ENDED", "SUSPENDED", "CLOSED",
})
PAPER_OBSERVATION_RETAINED_MATERIAL_TRANSITIONS = frozenset({
    "MONITORING_OPENED",
    "ENTRY_ACTIVATED",
    "STOP_TOUCHED",
    "TARGET_TOUCHED",
    "ORDERING_AMBIGUITY",
    "PROVIDER_MONITORING_GAP",
    "AUTHORITY_SUPERSEDED",
    "SPONSOR_STOPPED_MONITORING",
    "MONITORING_CLOSED",
})


class PaperObservationTrackState(StrEnum):
    AVAILABLE = "AVAILABLE"
    ACTIVE = "ACTIVE"
    MONITORING_INTERRUPTED = "MONITORING_INTERRUPTED"
    COMPLETE = "COMPLETE"
    OUTCOME_NOT_ESTABLISHED = "OUTCOME_NOT_ESTABLISHED"
    NOT_APPLICABLE_POSITION_ACTIVATED = "NOT_APPLICABLE_POSITION_ACTIVATED"


class PaperObservationMonitoringState(StrEnum):
    NOT_ACTIVE = "NOT_ACTIVE"
    ACTIVE = "ACTIVE"
    INTERRUPTED = "INTERRUPTED"
    COMPLETE = "COMPLETE"


class PaperObservationMonitoringApplicabilityState(StrEnum):
    OPEN = "OPEN"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class PaperObservationOutcome(StrEnum):
    ENTRY_NOT_OBSERVED = "ENTRY_NOT_OBSERVED"
    ENTRY_OBSERVED = "ENTRY_OBSERVED"
    STOP_LEVEL_TOUCHED = "STOP_LEVEL_TOUCHED"
    TARGET_LEVEL_TOUCHED = "TARGET_LEVEL_TOUCHED"
    BOTH_ORDERING_UNRESOLVED = "BOTH_ORDERING_UNRESOLVED"
    EXPIRED = "EXPIRED"
    OUTCOME_NOT_ESTABLISHED = "OUTCOME_NOT_ESTABLISHED"


class PaperObservationSourceKind(StrEnum):
    KITE_FACTUAL_TICK = "KITE_FACTUAL_TICK"
    COMPLETED_CANDLE = "COMPLETED_CANDLE"
    GAP_RECONCILIATION = "GAP_RECONCILIATION"


_BLOCKED_DISPOSITIONS = {
    SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE,
    SponsorActivationDisposition.BLOCKED_RISK_REJECTED,
    SponsorActivationDisposition.BLOCKED_CONSTRAINT,
    SponsorActivationDisposition.BLOCKED_MISSING_VALID_PLAN,
}
_TERMINAL_OUTCOMES = {
    PaperObservationOutcome.STOP_LEVEL_TOUCHED,
    PaperObservationOutcome.TARGET_LEVEL_TOUCHED,
    PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED,
}


@dataclass(frozen=True, slots=True)
class PaperObservationTrackV1:
    track_identity: str
    sponsor_decision_identity: str
    sponsor_decision_sha256: str
    sponsor_decision_timestamp: datetime
    decision_snapshot_identity: str
    decision_snapshot_sha256: str
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    direction: V1Direction
    step31_observation_identity: str
    step31_observation_sha256: str
    step31_contract_identity: str
    step31_contract_version: str
    step31_policy_identity: str
    step31_policy_version: str
    observation_entry_reference: Decimal | None
    entry_availability: str
    entry_condition: str | None
    stop: Decimal | None
    stop_availability: str
    target: Decimal | None
    target_availability: str
    invalidation: Decimal | None
    invalidation_availability: str
    step31_geometry_status: str
    risk_distance: Decimal | None
    reward_distance: Decimal | None
    risk_reward_ratio: Decimal | None
    risk_reward_state: str
    step31_severity: Step31WarningSeverity
    step31_warnings: tuple[str, ...]
    risk_identity: str | None
    risk_state: str
    activation_disposition: SponsorActivationDisposition
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_sha256: str
    contract_identity: str = PAPER_OBSERVATION_TRACK_CONTRACT_ID
    contract_version: str = PAPER_OBSERVATION_TRACK_CONTRACT_VERSION
    policy_identity: str = PAPER_OBSERVATION_TRACK_POLICY_ID
    policy_version: str = PAPER_OBSERVATION_TRACK_POLICY_VERSION
    authority: str = PAPER_OBSERVATION_TRACK_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not _identity(self.track_identity)
            or not _identity(self.sponsor_decision_identity)
            or not _digest(self.sponsor_decision_sha256)
            or not _aware(self.sponsor_decision_timestamp)
            or not _identity(self.decision_snapshot_identity)
            or not _digest(self.decision_snapshot_sha256)
            or not is_swing_analysis_run_id(self.native_run_identity)
            or not _instrument(self.canonical_instrument)
            or not _digest(self.native_assessment_sha256)
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not _identity(self.step31_observation_identity)
            or not _digest(self.step31_observation_sha256)
            or (self.step31_contract_identity, self.step31_contract_version) not in {
                (STEP31_OBSERVATION_CONTRACT_ID_V1, STEP31_OBSERVATION_CONTRACT_VERSION_V1),
                (STEP31_OBSERVATION_CONTRACT_ID, STEP31_OBSERVATION_CONTRACT_VERSION),
            }
            or self.step31_policy_identity != STEP31_OBSERVATION_POLICY_ID
            or self.step31_policy_version != STEP31_OBSERVATION_POLICY_VERSION
            or any(
                value is not None and not _finite(value)
                for value in (
                    self.observation_entry_reference,
                    self.stop,
                    self.target,
                    self.invalidation,
                )
            )
            or (self.observation_entry_reference is None) != (
                self.entry_condition is None
            )
            or (
                self.entry_condition is not None
                and self.entry_condition
                != (
                    f"SUBSEQUENT_DIRECTIONAL_CROSSING_ABOVE_{self.observation_entry_reference}"
                    if self.direction is V1Direction.LONG
                    else f"SUBSEQUENT_DIRECTIONAL_CROSSING_BELOW_{self.observation_entry_reference}"
                )
            )
            or any(
                availability != ("UNAVAILABLE" if value is None else "AVAILABLE")
                for value, availability in (
                    (self.observation_entry_reference, self.entry_availability),
                    (self.stop, self.stop_availability),
                    (self.target, self.target_availability),
                    (self.invalidation, self.invalidation_availability),
                )
            )
            or not _identity(self.step31_geometry_status)
            or any(
                value is not None and not _finite(value)
                for value in (
                    self.risk_distance,
                    self.reward_distance,
                    self.risk_reward_ratio,
                )
            )
            or not _identity(self.risk_reward_state)
            or type(self.step31_severity) is not Step31WarningSeverity
            or type(self.step31_warnings) is not tuple
            or any(not _identity(item) for item in self.step31_warnings)
            or (self.risk_identity is not None and not _identity(self.risk_identity))
            or self.risk_state not in {
                "RISK_UNAVAILABLE",
                "RISK_REJECTED",
                "RISK_CONSTRAINED",
                "RISK_APPROVED",
            }
            or self.activation_disposition not in _BLOCKED_DISPOSITIONS
            or not _aware(self.created_at)
            or self.created_at < self.sponsor_decision_timestamp
            or not self.provenance
            or any(not _identity(item) for item in self.provenance)
            or self.contract_identity != PAPER_OBSERVATION_TRACK_CONTRACT_ID
            or self.contract_version != PAPER_OBSERVATION_TRACK_CONTRACT_VERSION
            or self.policy_identity != PAPER_OBSERVATION_TRACK_POLICY_ID
            or self.policy_version != PAPER_OBSERVATION_TRACK_POLICY_VERSION
            or self.authority != PAPER_OBSERVATION_TRACK_AUTHORITY
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("PAPER_OBSERVATION_TRACK_INVALID")


@dataclass(frozen=True, slots=True)
class PaperObservationMarketFactV1:
    fact_identity: str
    track_identity: str
    canonical_instrument: str
    last_price: Decimal
    observed_at: datetime
    received_at: datetime
    source_identity: str
    source_sequence: int | None
    ordering_deterministic: bool
    recovered: bool
    integrity_sha256: str

    def __post_init__(self) -> None:
        if (
            not _identity(self.fact_identity)
            or not _identity(self.track_identity)
            or not _instrument(self.canonical_instrument)
            or not _finite(self.last_price)
            or self.last_price < 0
            or not _aware(self.observed_at)
            or not _aware(self.received_at)
            or self.observed_at > self.received_at
            or not _identity(self.source_identity)
            or (
                self.source_sequence is not None
                and (type(self.source_sequence) is not int or self.source_sequence < 0)
            )
            or type(self.ordering_deterministic) is not bool
            or type(self.recovered) is not bool
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("PAPER_OBSERVATION_MARKET_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class PaperObservationEventV1:
    event_identity: str
    track_identity: str
    outcome: PaperObservationOutcome
    observed_at: datetime
    recorded_at: datetime
    source_identity: str
    source_kind: PaperObservationSourceKind
    observed_price: Decimal | None
    interval_low: Decimal | None
    interval_high: Decimal | None
    integrity_sha256: str

    def __post_init__(self) -> None:
        interval = self.interval_low is not None or self.interval_high is not None
        if (
            not _identity(self.event_identity)
            or not _identity(self.track_identity)
            or self.outcome not in {
                PaperObservationOutcome.ENTRY_OBSERVED,
                *_TERMINAL_OUTCOMES,
                PaperObservationOutcome.OUTCOME_NOT_ESTABLISHED,
            }
            or not _aware(self.observed_at)
            or not _aware(self.recorded_at)
            or not _identity(self.source_identity)
            or type(self.source_kind) is not PaperObservationSourceKind
            or (self.observed_price is not None and not _finite(self.observed_price))
            or interval != (
                self.interval_low is not None and self.interval_high is not None
            )
            or (
                interval
                and (
                    not _finite(self.interval_low)
                    or not _finite(self.interval_high)
                    or self.interval_low > self.interval_high
                )
            )
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("PAPER_OBSERVATION_EVENT_INVALID")


@dataclass(frozen=True, slots=True)
class PaperObservationMonitoringRecordV1:
    record_identity: str
    track_identity: str
    state: PaperObservationMonitoringState
    reason: str
    recorded_at: datetime
    integrity_sha256: str

    def __post_init__(self) -> None:
        if (
            not _identity(self.record_identity)
            or not _identity(self.track_identity)
            or type(self.state) is not PaperObservationMonitoringState
            or not re.fullmatch(r"[A-Z0-9_]{1,96}", self.reason)
            or not _aware(self.recorded_at)
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("PAPER_OBSERVATION_MONITORING_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class PaperObservationMonitoringAuthorityV1:
    native_run_identity: str
    sponsor_decision_identity: str
    opportunity_identity: str
    material_revision: str
    native_assessment_sha256: str
    direction: V1Direction
    geometry_identity: str
    geometry_sha256: str
    review_authority_identity: str
    decision_authority_identity: str
    canonical_instrument: str
    instrument_contract_identity: str
    monitoring_boundary_identity: str
    monitoring_window_identity: str
    capability_requirements: tuple[str, ...]
    policy_identity: str
    policy_version: str

    def __post_init__(self) -> None:
        if (
            not is_swing_analysis_run_id(self.native_run_identity)
            or not _identity(self.sponsor_decision_identity)
            or not _identity(self.opportunity_identity)
            or not _identity(self.material_revision)
            or not _digest(self.native_assessment_sha256)
            or type(self.direction) is not V1Direction
            or not _identity(self.geometry_identity)
            or not _digest(self.geometry_sha256)
            or not _identity(self.review_authority_identity)
            or not _identity(self.decision_authority_identity)
            or not _instrument(self.canonical_instrument)
            or not _identity(self.instrument_contract_identity)
            or not _identity(self.monitoring_boundary_identity)
            or not _identity(self.monitoring_window_identity)
            or type(self.capability_requirements) is not tuple
            or not self.capability_requirements
            or any(not _identity(item) for item in self.capability_requirements)
            or not _identity(self.policy_identity)
            or not _identity(self.policy_version)
        ):
            raise ValueError("PAPER_OBSERVATION_MONITORING_AUTHORITY_INVALID")


@dataclass(frozen=True, slots=True)
class PaperObservationMonitoringApplicabilityV1:
    record_identity: str
    track_identity: str
    state: PaperObservationMonitoringApplicabilityState
    reason: str
    authority: PaperObservationMonitoringAuthorityV1
    predecessor_applicability_identity: str | None
    recorded_at: datetime
    integrity_sha256: str
    contract_identity: str = PAPER_OBSERVATION_MONITORING_APPLICABILITY_CONTRACT_ID
    contract_version: str = PAPER_OBSERVATION_MONITORING_APPLICABILITY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not _identity(self.record_identity)
            or not _identity(self.track_identity)
            or type(self.state) is not PaperObservationMonitoringApplicabilityState
            or not re.fullmatch(r"[A-Z0-9_]{1,96}", self.reason)
            or type(self.authority) is not PaperObservationMonitoringAuthorityV1
            or (
                self.predecessor_applicability_identity is not None
                and not _identity(self.predecessor_applicability_identity)
            )
            or not _aware(self.recorded_at)
            or self.contract_identity
            != PAPER_OBSERVATION_MONITORING_APPLICABILITY_CONTRACT_ID
            or self.contract_version
            != PAPER_OBSERVATION_MONITORING_APPLICABILITY_CONTRACT_VERSION
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("PAPER_OBSERVATION_MONITORING_APPLICABILITY_INVALID")


@dataclass(frozen=True, slots=True)
class PaperObservationMonitoringApplicabilityProjectionV1:
    state: PaperObservationMonitoringApplicabilityState
    operation: str
    automatic_restoration: bool
    reason_codes: tuple[str, ...]
    record_identity: str | None

    def __post_init__(self) -> None:
        if (
            type(self.state) is not PaperObservationMonitoringApplicabilityState
            or self.operation not in {
                "AUTOMATIC_RESTORATION_ALLOWED",
                "RECOVERY_REQUIRED",
                "MONITORING_CLOSED",
            }
            or type(self.automatic_restoration) is not bool
            or not self.reason_codes
            or any(not re.fullmatch(r"[A-Z0-9_]{1,96}", item) for item in self.reason_codes)
            or (self.record_identity is not None and not _identity(self.record_identity))
            or self.automatic_restoration
            != (
                self.state is PaperObservationMonitoringApplicabilityState.OPEN
                and self.operation == "AUTOMATIC_RESTORATION_ALLOWED"
            )
        ):
            raise ValueError("PAPER_OBSERVATION_MONITORING_APPLICABILITY_PROJECTION_INVALID")


@dataclass(frozen=True, slots=True)
class PaperObservationTrackProjectionV1:
    track: PaperObservationTrackV1
    track_state: PaperObservationTrackState
    monitoring_state: PaperObservationMonitoringState
    entry_state: PaperObservationOutcome
    latest_event: PaperObservationOutcome
    outcome_state: PaperObservationOutcome
    event_identities: tuple[str, ...]
    created_at: datetime
    last_factual_observation_at: datetime | None
    monitoring_reason: str

    history_representation: str = "RAW_HISTORY"
    raw_detail_availability: str = "RAW_RECORDS_VALIDATED"
    first_factual_observation_at: datetime | None = None
    historical_fact_count: int | None = None
    historical_source_count: int | None = None
    historical_source_sha256: str | None = None
    historical_consolidation_identity: str | None = None
    historical_detail_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PaperObservationRestorationProjectionV1:
    """Exact control state needed to restore monitoring, without market facts."""

    track_identity: str
    canonical_instrument: str
    track_authority: str
    track_integrity_sha256: str
    sponsor_decision_identity: str
    decision_snapshot_identity: str
    native_run_identity: str
    terminal: bool
    latest_event: PaperObservationOutcome
    latest_event_identity: str | None
    monitoring_state: PaperObservationMonitoringState
    monitoring_reason: str
    monitoring_record_identity: str | None
    applicability: PaperObservationMonitoringApplicabilityProjectionV1

    def __post_init__(self) -> None:
        if (
            not _identity(self.track_identity)
            or not _instrument(self.canonical_instrument)
            or self.track_authority != PAPER_OBSERVATION_TRACK_AUTHORITY
            or not _digest(self.track_integrity_sha256)
            or not _identity(self.sponsor_decision_identity)
            or not _identity(self.decision_snapshot_identity)
            or not is_swing_analysis_run_id(self.native_run_identity)
            or type(self.terminal) is not bool
            or type(self.latest_event) is not PaperObservationOutcome
            or (
                self.latest_event_identity is not None
                and not _identity(self.latest_event_identity)
            )
            or type(self.monitoring_state) is not PaperObservationMonitoringState
            or not re.fullmatch(r"[A-Z0-9_]{1,96}", self.monitoring_reason)
            or (
                self.monitoring_record_identity is not None
                and not _identity(self.monitoring_record_identity)
            )
            or type(self.applicability)
            is not PaperObservationMonitoringApplicabilityProjectionV1
            or self.terminal != (self.latest_event in _TERMINAL_OUTCOMES)
        ):
            raise ValueError("PAPER_OBSERVATION_RESTORATION_PROJECTION_INVALID")


def make_monitoring_applicability(
    track_identity: str,
    state: PaperObservationMonitoringApplicabilityState,
    reason: str,
    authority: PaperObservationMonitoringAuthorityV1,
    recorded_at: datetime,
    *,
    predecessor_applicability_identity: str | None = None,
) -> PaperObservationMonitoringApplicabilityV1:
    identity = "PAPER-OBSERVATION-APPLICABILITY-" + sha256(
        (
            f"{track_identity}:{state.value}:{reason}:"
            f"{predecessor_applicability_identity}:"
            f"{_canonical(authority).decode('utf-8')}"
        ).encode("utf-8")
    ).hexdigest()
    values = dict(
        record_identity=identity,
        track_identity=track_identity,
        state=state,
        reason=reason,
        authority=authority,
        predecessor_applicability_identity=predecessor_applicability_identity,
        recorded_at=recorded_at,
        integrity_sha256="",
        contract_identity=PAPER_OBSERVATION_MONITORING_APPLICABILITY_CONTRACT_ID,
        contract_version=PAPER_OBSERVATION_MONITORING_APPLICABILITY_CONTRACT_VERSION,
    )
    return PaperObservationMonitoringApplicabilityV1(**(
        values | {"integrity_sha256": _values_digest(values)}
    ))


def paper_observation_instrument_contract_identity(
    *,
    canonical_instrument: str,
    provider: str,
    exchange: str,
    segment: str,
    trading_symbol: str,
    instrument_type: str,
    expiry: str | None,
) -> str:
    """Return the exact non-secret derivative contract used by admission/restore."""

    values = {
        "canonical_instrument": canonical_instrument,
        "provider": provider,
        "exchange": exchange,
        "segment": segment,
        "trading_symbol": trading_symbol,
        "instrument_type": instrument_type,
        "expiry": expiry,
    }
    if (
        not _instrument(canonical_instrument)
        or any(not _identity(values[name]) for name in (
            "provider", "exchange", "segment", "trading_symbol"
        ))
        or type(instrument_type) is not str
        or (expiry is not None and (type(expiry) is not str or not expiry))
    ):
        raise ValueError("PAPER_OBSERVATION_INSTRUMENT_CONTRACT_INVALID")
    return "PAPER-OBSERVATION-INSTRUMENT-" + _values_digest(values)


def project_monitoring_applicability(
    retained: PaperObservationMonitoringApplicabilityV1 | None,
    current_authority: PaperObservationMonitoringAuthorityV1 | None,
) -> PaperObservationMonitoringApplicabilityProjectionV1:
    """Fail closed unless one retained applicability record is exactly compatible."""

    if retained is None:
        return PaperObservationMonitoringApplicabilityProjectionV1(
            state=PaperObservationMonitoringApplicabilityState.SUSPENDED,
            operation="RECOVERY_REQUIRED",
            automatic_restoration=False,
            reason_codes=("APPLICABILITY_RECORD_UNAVAILABLE",),
            record_identity=None,
        )
    if retained.state is PaperObservationMonitoringApplicabilityState.CLOSED:
        return PaperObservationMonitoringApplicabilityProjectionV1(
            state=retained.state,
            operation="MONITORING_CLOSED",
            automatic_restoration=False,
            reason_codes=(retained.reason,),
            record_identity=retained.record_identity,
        )
    if retained.state is PaperObservationMonitoringApplicabilityState.SUSPENDED:
        return PaperObservationMonitoringApplicabilityProjectionV1(
            state=retained.state,
            operation="RECOVERY_REQUIRED",
            automatic_restoration=False,
            reason_codes=(retained.reason,),
            record_identity=retained.record_identity,
        )
    if current_authority is None:
        return PaperObservationMonitoringApplicabilityProjectionV1(
            state=PaperObservationMonitoringApplicabilityState.SUSPENDED,
            operation="RECOVERY_REQUIRED",
            automatic_restoration=False,
            reason_codes=("CURRENT_AUTHORITY_UNPROVEN",),
            record_identity=retained.record_identity,
        )
    comparisons = (
        ("SPONSOR_DECISION_INCOMPATIBLE", "sponsor_decision_identity"),
        ("OPPORTUNITY_IDENTITY_INCOMPATIBLE", "opportunity_identity"),
        ("MATERIAL_REVISION_INCOMPATIBLE", "material_revision"),
        ("NATIVE_ASSESSMENT_INCOMPATIBLE", "native_assessment_sha256"),
        ("DIRECTION_INCOMPATIBLE", "direction"),
        ("GEOMETRY_IDENTITY_INCOMPATIBLE", "geometry_identity"),
        ("GEOMETRY_INCOMPATIBLE", "geometry_sha256"),
        ("REVIEW_AUTHORITY_INCOMPATIBLE", "review_authority_identity"),
        ("DECISION_AUTHORITY_INCOMPATIBLE", "decision_authority_identity"),
        ("INSTRUMENT_INCOMPATIBLE", "canonical_instrument"),
        ("INSTRUMENT_CONTRACT_INCOMPATIBLE", "instrument_contract_identity"),
        ("MONITORING_BOUNDARY_INCOMPATIBLE", "monitoring_boundary_identity"),
        ("MONITORING_WINDOW_INCOMPATIBLE", "monitoring_window_identity"),
        ("CAPABILITY_REQUIREMENTS_INCOMPATIBLE", "capability_requirements"),
        ("POLICY_IDENTITY_INCOMPATIBLE", "policy_identity"),
        ("POLICY_VERSION_INCOMPATIBLE", "policy_version"),
    )
    reasons = tuple(
        reason
        for reason, field in comparisons
        if getattr(retained.authority, field) != getattr(current_authority, field)
    )
    if reasons:
        return PaperObservationMonitoringApplicabilityProjectionV1(
            state=PaperObservationMonitoringApplicabilityState.SUSPENDED,
            operation="RECOVERY_REQUIRED",
            automatic_restoration=False,
            reason_codes=reasons,
            record_identity=retained.record_identity,
        )
    return PaperObservationMonitoringApplicabilityProjectionV1(
        state=PaperObservationMonitoringApplicabilityState.OPEN,
        operation="AUTOMATIC_RESTORATION_ALLOWED",
        automatic_restoration=True,
        reason_codes=("CURRENT_AUTHORITY_COMPATIBLE",),
        record_identity=retained.record_identity,
    )


def create_paper_observation_track(
    result: SponsorObservationDecisionResult,
    *,
    current_run_identity: str,
    created_at: datetime,
) -> PaperObservationTrackV1:
    """Bind one exact blocked PAPER decision without granting position authority."""

    if (
        type(result) is not SponsorObservationDecisionResult
        or result.decision.choice is not SponsorTradeChoice.PAPER
        or result.activation.disposition not in _BLOCKED_DISPOSITIONS
        or result.activation.sponsor_position_identity is not None
        or result.activation.existing_sponsor_decision_identity is not None
        or current_run_identity != result.snapshot.native_run_identity
        or result.decision.snapshot_identity != result.snapshot.snapshot_identity
        or result.decision.snapshot_sha256 != result.snapshot.integrity_sha256
        or result.activation.decision_identity != result.decision.decision_identity
        or not _aware(created_at)
        or created_at < result.decision.decision_timestamp
    ):
        raise ValueError("PAPER_OBSERVATION_TRACK_TRUST_BINDING_INVALID")
    track_identity = "PAPER-OBSERVATION-TRACK-" + sha256(
        (
            f"{PAPER_OBSERVATION_TRACK_CONTRACT_ID}:"
            f"{result.decision.decision_identity}:"
            f"{result.snapshot.step31_observation_identity}"
        ).encode("utf-8")
    ).hexdigest()
    values = dict(
        track_identity=track_identity,
        sponsor_decision_identity=result.decision.decision_identity,
        sponsor_decision_sha256=result.decision.integrity_sha256,
        sponsor_decision_timestamp=result.decision.decision_timestamp,
        decision_snapshot_identity=result.snapshot.snapshot_identity,
        decision_snapshot_sha256=result.snapshot.integrity_sha256,
        native_run_identity=result.snapshot.native_run_identity,
        canonical_instrument=result.snapshot.canonical_instrument,
        native_assessment_sha256=result.snapshot.native_assessment_sha256,
        direction=result.snapshot.direction,
        step31_observation_identity=result.snapshot.step31_observation_identity,
        step31_observation_sha256=result.snapshot.step31_observation_sha256,
        step31_contract_identity=STEP31_OBSERVATION_CONTRACT_ID,
        step31_contract_version=STEP31_OBSERVATION_CONTRACT_VERSION,
        step31_policy_identity=STEP31_OBSERVATION_POLICY_ID,
        step31_policy_version=STEP31_OBSERVATION_POLICY_VERSION,
        observation_entry_reference=result.snapshot.entry,
        entry_availability=(
            "UNAVAILABLE" if result.snapshot.entry is None else "AVAILABLE"
        ),
        entry_condition=(
            None
            if result.snapshot.entry is None
            else (
                f"SUBSEQUENT_DIRECTIONAL_CROSSING_ABOVE_{result.snapshot.entry}"
                if result.snapshot.direction is V1Direction.LONG
                else f"SUBSEQUENT_DIRECTIONAL_CROSSING_BELOW_{result.snapshot.entry}"
            )
        ),
        stop=result.snapshot.stop,
        stop_availability=(
            "UNAVAILABLE" if result.snapshot.stop is None else "AVAILABLE"
        ),
        target=result.snapshot.target,
        target_availability=(
            "UNAVAILABLE" if result.snapshot.target is None else "AVAILABLE"
        ),
        invalidation=result.snapshot.invalidation,
        invalidation_availability=(
            "UNAVAILABLE" if result.snapshot.invalidation is None else "AVAILABLE"
        ),
        step31_geometry_status=result.snapshot.step31_geometry_status,
        risk_distance=result.snapshot.risk_distance,
        reward_distance=result.snapshot.reward_distance,
        risk_reward_ratio=result.snapshot.risk_reward_ratio,
        risk_reward_state=result.snapshot.risk_reward_state,
        step31_severity=result.snapshot.step31_severity,
        step31_warnings=result.snapshot.step31_warnings,
        risk_identity=result.snapshot.risk_identity,
        risk_state=result.snapshot.risk_state,
        activation_disposition=result.activation.disposition,
        created_at=created_at,
        provenance=(
            "ADR-0016",
            result.decision.integrity_sha256,
            result.snapshot.integrity_sha256,
            result.snapshot.step31_observation_sha256,
        ),
        integrity_sha256="",
        contract_identity=PAPER_OBSERVATION_TRACK_CONTRACT_ID,
        contract_version=PAPER_OBSERVATION_TRACK_CONTRACT_VERSION,
        policy_identity=PAPER_OBSERVATION_TRACK_POLICY_ID,
        policy_version=PAPER_OBSERVATION_TRACK_POLICY_VERSION,
        authority=PAPER_OBSERVATION_TRACK_AUTHORITY,
    )
    return PaperObservationTrackV1(**(
        values | {"integrity_sha256": _values_digest(values)}
    ))


@dataclass(frozen=True, slots=True)
class PaperObservationCompactStateV1:
    track_identity: str
    track_sha256: str
    decision_identity: str
    applicability_identity: str
    applicability_sha256: str
    authority: PaperObservationMonitoringAuthorityV1
    entry: Decimal | None
    stop: Decimal | None
    target: Decimal | None
    monitoring_generation: str
    latest_observation: str | None
    observation_sha256: str | None
    last_price: Decimal | None
    observed_at: datetime | None
    sequence: int | None
    session: str | None
    entry_at: datetime | None
    stop_at: datetime | None
    target_at: datetime | None
    outcome: PaperObservationOutcome
    high: Decimal | None
    low: Decimal | None
    coverage_start: datetime | None
    coverage_end: datetime | None
    gap_count: int
    latest_gap_identity: str | None
    monitoring_state: PaperObservationMonitoringState
    monitoring_reason: str
    material_head: str | None
    material_count: int
    predecessor_sha256: str | None
    integrity_sha256: str
    schema: str = COMPACT_SCHEMA
    version: str = "1"
    policy: str = COMPACT_POLICY
    resume_after_gap: bool = False
    reconciled_price: Decimal | None = None
    latest_reconciliation: str | None = None
    excursion_state: str = "UNAVAILABLE_NOT_DEFINED_BY_TRACK_V1"

    def __post_init__(self) -> None:
        if (
            self.schema != COMPACT_SCHEMA or self.version != "1"
            or self.policy != COMPACT_POLICY
            or self.excursion_state != "UNAVAILABLE_NOT_DEFINED_BY_TRACK_V1"
            or type(self.resume_after_gap) is not bool
            or (self.reconciled_price is not None and not _finite(self.reconciled_price))
            or not all(_identity(v) for v in (
                self.track_identity, self.decision_identity,
                self.applicability_identity, self.monitoring_generation,
            ))
            or not all(_digest(v) for v in (
                self.track_sha256, self.applicability_sha256, self.integrity_sha256,
            ))
            or type(self.authority) is not PaperObservationMonitoringAuthorityV1
            or type(self.outcome) is not PaperObservationOutcome
            or type(self.monitoring_state) is not PaperObservationMonitoringState
            or not re.fullmatch(r"[A-Z0-9_]{1,96}", self.monitoring_reason)
            or any(v is not None and not _finite(v) for v in (
                self.entry, self.stop, self.target, self.last_price, self.high, self.low,
            ))
            or any(v is not None and not _aware(v) for v in (
                self.observed_at, self.entry_at, self.stop_at, self.target_at,
                self.coverage_start, self.coverage_end,
            ))
            or any(v is not None and not _digest(v) for v in (
                self.material_head, self.predecessor_sha256,
                self.observation_sha256, self.latest_gap_identity,
            ))
            or type(self.gap_count) is not int or self.gap_count < 0
            or type(self.material_count) is not int or self.material_count < 0
            or (self.sequence is not None and (type(self.sequence) is not int or self.sequence < 0))
            or (self.high is None) != (self.low is None)
            or (self.high is not None and self.low > self.high)
            or (self.latest_observation is None) != (self.observation_sha256 is None)
            or (self.latest_observation is not None and (
                len(self.latest_observation) > 8192
                or sha256(self.latest_observation.encode()).hexdigest() != self.observation_sha256
                or self.last_price is None or self.observed_at is None or self.session is None
            ))
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("PAPER_OBSERVATION_COMPACT_RECOVERY_REQUIRED")
        if self.latest_observation is not None:
            try:
                observation = json.loads(self.latest_observation)
                tick = observation["tick"]
                instrument = tick["instrument"]
                observed = datetime.fromisoformat(tick["observed_at"])
                received = datetime.fromisoformat(tick["received_at"])
                contract = paper_observation_instrument_contract_identity(
                    canonical_instrument=self.authority.canonical_instrument,
                    **{key: instrument[key] for key in (
                        "provider", "exchange", "segment", "trading_symbol",
                        "instrument_type", "expiry")})
                if (set(observation) != {"generation", "tick"}
                        or set(tick) != {"instrument", "last_price", "observed_at", "received_at",
                            "source", "connection_id", "source_sequence", "previous_interval_available",
                            "session_continuous", "ordering_deterministic", "recovered"}
                        or observation["generation"] != self.monitoring_generation
                        or Decimal(tick["last_price"]) != self.last_price
                        or observed != self.observed_at or not _aware(received) or received < observed
                        or tick["source_sequence"] != self.sequence or tick["connection_id"] != self.session
                        or tick["source"] != "KITE_CONNECT_WEBSOCKET"
                        or contract != self.authority.instrument_contract_identity
                        or any(type(tick[name]) is not bool for name in (
                            "previous_interval_available", "session_continuous", "ordering_deterministic", "recovered"))):
                    raise ValueError
            except (TypeError, KeyError, ValueError, ArithmeticError) as error:
                raise ValueError("PAPER_OBSERVATION_COMPACT_RECOVERY_REQUIRED") from error
        if self.latest_reconciliation is not None:
            try:
                record = json.loads(self.latest_reconciliation)
                if (len(self.latest_reconciliation) > 8192
                        or set(record) != {"source_identity", "source_kind", "boundary", "low", "high", "open", "close"}
                        or not _identity(record["source_identity"])
                        or record["source_kind"] not in {"COMPLETED_CANDLE", "GAP_RECONCILIATION"}
                        or not _aware(datetime.fromisoformat(record["boundary"]))
                        or any(not Decimal(record[key]).is_finite() for key in ("low", "high"))
                        or Decimal(record["low"]) > Decimal(record["high"])
                        or (record["open"] is None) != (record["close"] is None)
                        or any(value is not None and not (
                            Decimal(record["low"]) <= Decimal(value) <= Decimal(record["high"]))
                            for value in (record["open"], record["close"]))):
                    raise ValueError
            except (TypeError, KeyError, ValueError, ArithmeticError) as error:
                raise ValueError("PAPER_OBSERVATION_COMPACT_RECOVERY_REQUIRED") from error

    @property
    def terminal(self) -> bool:
        return self.outcome in _TERMINAL_OUTCOMES


def compact_replace(state: PaperObservationCompactStateV1, **changes):
    values = {name: getattr(state, name) for name in state.__dataclass_fields__}
    values.update(changes)
    values["predecessor_sha256"] = state.integrity_sha256
    values["integrity_sha256"] = ""
    values["integrity_sha256"] = _values_digest(values)
    return PaperObservationCompactStateV1(**values)


def initial_compact_state(track, applicability):
    values = dict(
        track_identity=track.track_identity, track_sha256=track.integrity_sha256,
        decision_identity=track.sponsor_decision_identity,
        applicability_identity=applicability.record_identity,
        applicability_sha256=applicability.integrity_sha256,
        authority=applicability.authority, entry=track.observation_entry_reference,
        stop=track.stop, target=track.target, monitoring_generation="UNREGISTERED",
        latest_observation=None, observation_sha256=None, last_price=None,
        observed_at=None, sequence=None, session=None, entry_at=None,
        stop_at=None, target_at=None, outcome=PaperObservationOutcome.ENTRY_NOT_OBSERVED,
        high=None, low=None, coverage_start=None, coverage_end=None,
        gap_count=0, latest_gap_identity=None,
        monitoring_state=PaperObservationMonitoringState.NOT_ACTIVE,
        monitoring_reason="MONITORING_CAPABILITY_NOT_YET_REGISTERED",
        material_head=None, material_count=0, predecessor_sha256=None,
        integrity_sha256="", schema=COMPACT_SCHEMA, version="1", policy=COMPACT_POLICY,
        resume_after_gap=False, reconciled_price=None, latest_reconciliation=None,
        excursion_state="UNAVAILABLE_NOT_DEFINED_BY_TRACK_V1",
    )
    values["integrity_sha256"] = _values_digest(values)
    return PaperObservationCompactStateV1(**values)


def compact_projection(track, state):
    return PaperObservationTrackProjectionV1(
        track=track,
        track_state=(PaperObservationTrackState.COMPLETE if state.terminal else
            PaperObservationTrackState.MONITORING_INTERRUPTED
            if state.monitoring_state is PaperObservationMonitoringState.INTERRUPTED
            else PaperObservationTrackState.ACTIVE),
        monitoring_state=state.monitoring_state,
        entry_state=(PaperObservationOutcome.ENTRY_NOT_OBSERVED if state.entry_at is None
                     else PaperObservationOutcome.ENTRY_OBSERVED),
        latest_event=state.outcome, outcome_state=state.outcome,
        event_identities=() if state.material_head is None else (state.material_head,),
        created_at=track.created_at, last_factual_observation_at=state.coverage_end,
        monitoring_reason=state.monitoring_reason,
        history_representation="CURRENT_COMPACT",
        raw_detail_availability="NOT_RETAINED_PROSPECTIVE_POLICY",
    )


def _compact_from_dict(value):
    data = dict(value)
    authority = dict(data["authority"])
    authority["direction"] = V1Direction(authority["direction"])
    authority["capability_requirements"] = tuple(authority["capability_requirements"])
    data["authority"] = PaperObservationMonitoringAuthorityV1(**authority)
    for name in ("entry", "stop", "target", "last_price", "high", "low", "reconciled_price"):
        data[name] = None if data[name] is None else Decimal(data[name])
    for name in ("observed_at", "entry_at", "stop_at", "target_at", "coverage_start", "coverage_end"):
        data[name] = None if data[name] is None else datetime.fromisoformat(data[name])
    data["outcome"] = PaperObservationOutcome(data["outcome"])
    data["monitoring_state"] = PaperObservationMonitoringState(data["monitoring_state"])
    return PaperObservationCompactStateV1(**data)


@dataclass(frozen=True, slots=True)
class PaperObservationHistoricalConsolidationV1:
    """Prepared immutable research bytes; deliberately not a live checkpoint."""

    identity: str
    integrity_sha256: str
    canonical_bytes: bytes


def _consolidation_sorted(rows):
    """External two-way merge, 128 rows per run and logarithmic run handles.

    Only private temporary scratch is written. Neither the evidence tree nor
    the full-history validated-object cache participates in this operation.
    """
    with TemporaryDirectory(prefix="kronos-consolidation-") as scratch:
        root = Path(scratch)
        levels = []
        serial = 0

        def merge(left, right, output):
            with left.open("rb") as a, right.open("rb") as b, output.open("wb") as dest:
                x, y = a.readline(), b.readline()
                while x and y:
                    if json.loads(x)[0] <= json.loads(y)[0]:
                        dest.write(x)
                        x = a.readline()
                    else:
                        dest.write(y)
                        y = b.readline()
                if x:
                    dest.write(x)
                if y:
                    dest.write(y)
                for line in a:
                    dest.write(line)
                for line in b:
                    dest.write(line)
            left.unlink()
            right.unlink()

        iterator = iter(rows)
        while True:
            batch = []
            for _ in range(128):
                row = next(iterator, None)
                if row is None:
                    break
                batch.append(row)
            if not batch:
                break
            path = root / str(serial)
            serial += 1
            with path.open("wb") as output:
                for row in sorted(batch, key=lambda item: item[0]):
                    output.write(_canonical(row) + b"\n")
            level = 0
            while level < len(levels) and levels[level] is not None:
                merged = root / str(serial)
                serial += 1
                merge(levels[level], path, merged)
                levels[level] = None
                path = merged
                level += 1
            if level == len(levels):
                levels.append(path)
            else:
                levels[level] = path
        result = None
        for path in levels:
            if path is not None:
                if result is None:
                    result = path
                else:
                    merged = root / str(serial)
                    serial += 1
                    merge(result, path, merged)
                    result = merged
        if result is not None:
            with result.open("rb") as source:
                for line in source:
                    yield json.loads(line)


class LocalPaperObservationTrackStore:
    """Append-only Track, factual-observation, event, and transport evidence."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("PAPER_OBSERVATION_STORE_INVALID")
        self._lock = RLock()
        self._validated_facts = ValidatedBytesReuse()
        self._compact_tokens = {}
        self._compact_open = set()

    def is_compact(self, track_identity):
        generation = _read(self._track_path(track_identity)).get("storage_generation")
        if generation not in (None, COMPACT_SCHEMA):
            raise ValueError("PAPER_OBSERVATION_STORAGE_GENERATION_INVALID")
        return generation == COMPACT_SCHEMA

    def prepare_historical_consolidation(
        self, track_identity: str, *, created_at: datetime,
    ) -> PaperObservationHistoricalConsolidationV1:
        """Explicit read-only maintenance, never called by operational paths.

        The caller freezes the creation boundary for the maintenance operation;
        replays use that same boundary. No publication/deletion API is granted.
        Memory scales with control records, not the historical tick population.
        """
        if (not re.fullmatch(r"PAPER-OBSERVATION-TRACK-[0-9a-f]{64}", track_identity)
                or not _aware(created_at)):
            raise ValueError("PAPER_CONSOLIDATION_REQUEST_INVALID")
        directory = self.root / track_identity
        if directory.is_symlink() or self.is_compact(track_identity):
            raise ValueError("PAPER_CONSOLIDATION_LEGACY_ONLY")
        track = self.load_track(track_identity)
        if track.track_identity != track_identity:
            raise ValueError("PAPER_CONSOLIDATION_BINDING_INVALID")

        def paths():
            # Exact closed legacy inventory: prospective applicability/checkpoints
            # and unexpected files fail closed rather than being silently ignored.
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        raise ValueError("PAPER_CONSOLIDATION_SOURCE_INVALID")
                    if entry.name == "track.json" and entry.is_file():
                        yield [entry.name, None]
                    elif entry.name in {"facts", "events", "monitoring"} and entry.is_dir():
                        with os.scandir(entry.path) as children:
                            for child in children:
                                if (child.is_symlink() or not child.is_file()
                                        or not child.name.endswith(".json")):
                                    raise ValueError("PAPER_CONSOLIDATION_SOURCE_INVALID")
                                yield [f"{entry.name}/{child.name}", None]
                    else:
                        raise ValueError("PAPER_CONSOLIDATION_NOT_HISTORICAL")

        digest = sha256()
        inventory = sha256()
        count = 0
        events, monitoring = [], []

        def inventory_row(relative):
            path = directory / relative
            before = self._file_token(path)
            encoded = path.read_bytes()
            after = self._file_token(path)
            if before != after or path.is_symlink():
                raise ValueError("PAPER_CONSOLIDATION_SOURCE_CHANGED")
            row = [relative, len(encoded), sha256(encoded).hexdigest()]
            metadata = [*row, *before]
            return encoded, row, metadata

        def facts():
            nonlocal count
            for relative, _ in _consolidation_sorted(paths()):
                encoded, row, metadata = inventory_row(relative)
                digest.update(_canonical(row) + b"\n")
                inventory.update(_canonical(metadata) + b"\n")
                count += 1
                if relative == "track.json":
                    if _track_from_dict(json.loads(encoded)["track"]) != track:
                        raise ValueError("PAPER_CONSOLIDATION_SOURCE_CHANGED")
                    continue
                kind = relative.split("/")[0]
                if kind == "facts":
                    # Same decoder/integrity validator as full history, no cache.
                    record = _fact_from_bytes(encoded)
                    identity = record.fact_identity
                    if record.canonical_instrument != track.canonical_instrument:
                        raise ValueError("PAPER_CONSOLIDATION_BINDING_INVALID")
                else:
                    payload = json.loads(encoded)
                    if payload.get("schema") != PAPER_OBSERVATION_TRACK_STORE_SCHEMA:
                        raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID")
                    if kind == "events":
                        record = _event_from_dict(payload["event"])
                        identity = record.event_identity
                        events.append(record)
                    else:
                        record = _monitoring_from_dict(payload["monitoring"])
                        identity = record.record_identity
                        monitoring.append(record)
                if (record.track_identity != track_identity
                        or relative != f"{kind}/{identity}.json"):
                    raise ValueError("PAPER_CONSOLIDATION_BINDING_INVALID")
                if kind == "facts":
                    yield [record.source_identity, _primitive(record)]

        total = unsequenced = recovered = unordered = 0
        first = last = previous = None
        low = high = None
        last_prices_agree = True
        latest_retained_at = track.created_at
        for _, data in _consolidation_sorted(facts()):
            fact = _fact_from_dict(data)
            if previous is not None and previous.source_identity == fact.source_identity:
                code = ("DUPLICATE_SOURCE" if (previous.last_price, previous.observed_at)
                        == (fact.last_price, fact.observed_at) else "PROVIDER_SEQUENCE_CONFLICT")
                raise ValueError(f"PAPER_CONSOLIDATION_{code}")
            previous = fact
            total += 1
            unsequenced += fact.source_sequence is None
            recovered += fact.recovered
            unordered += not fact.ordering_deterministic
            low = fact.last_price if low is None else min(low, fact.last_price)
            high = fact.last_price if high is None else max(high, fact.last_price)
            latest_retained_at = max(latest_retained_at, fact.received_at)
            if first is None or (fact.observed_at, fact.fact_identity) < (first.observed_at, first.fact_identity):
                first = fact
            if last is None or fact.observed_at > last.observed_at:
                last, last_prices_agree = fact, True
            elif fact.observed_at == last.observed_at:
                last_prices_agree &= fact.last_price == last.last_price
                if fact.fact_identity > last.fact_identity:
                    last = fact
        if not total:
            raise ValueError("PAPER_CONSOLIDATION_EMPTY_HISTORY")
        # Existing event ordering; no replay of analytical rules or inferred touch.
        rank = {PaperObservationOutcome.ENTRY_OBSERVED: 0,
                PaperObservationOutcome.OUTCOME_NOT_ESTABLISHED: 2}
        events.sort(key=lambda x: (x.observed_at, x.recorded_at, rank.get(x.outcome, 1), x.event_identity))
        monitoring.sort(key=lambda x: (x.recorded_at, x.record_identity))
        for record in (*events, *monitoring):
            latest_retained_at = max(latest_retained_at, record.recorded_at)
        if created_at < latest_retained_at:
            raise ValueError("PAPER_CONSOLIDATION_CREATION_BOUNDARY_INVALID")
        terminal = next((item for item in reversed(events) if item.outcome in _TERMINAL_OUTCOMES), None)
        if terminal is not None and terminal != events[-1]:
            raise ValueError("PAPER_CONSOLIDATION_TERMINAL_HISTORY_CONFLICT")
        latest_monitor = monitoring[-1] if monitoring else None
        interrupted = latest_monitor is not None and latest_monitor.state is PaperObservationMonitoringState.INTERRUPTED
        reasons = {}
        interruptions = recoveries = 0
        was_interrupted = False
        for item in monitoring:
            reasons[item.reason] = reasons.get(item.reason, 0) + 1
            interruptions += item.state is PaperObservationMonitoringState.INTERRUPTED
            recoveries += was_interrupted and item.state is PaperObservationMonitoringState.ACTIVE
            was_interrupted = item.state is PaperObservationMonitoringState.INTERRUPTED
        verified = sha256()
        verified_count = 0
        for relative, _ in _consolidation_sorted(paths()):
            _, _, metadata = inventory_row(relative)
            verified.update(_canonical(metadata) + b"\n")
            verified_count += 1
        if verified_count != count or verified.digest() != inventory.digest():
            raise ValueError("PAPER_CONSOLIDATION_SOURCE_CHANGED")
        values = dict(
            schema="KRONOS-PAPER-OBSERVATION-HISTORICAL-CONSOLIDATION-V1",
            policy="VALIDATED-LEGACY-RESEARCH-CONSOLIDATION-V1", implementation_version="1",
            created_at=created_at.astimezone(UTC), track=_primitive(track),
            authority="RESEARCH_ONLY", currentness="HISTORICAL_NO_CURRENT_APPLICABILITY",
            monitoring_restorable=False, deletion_ready=False,
            deletion_readiness="PENDING_REFERENCE_SCAN", applicability=None,
            market=None, instrument_contract=None, review_identity=None, requirement_identity=None,
            opportunity_identity=None, material_revision=None,
            unavailable_bindings_reason="NOT_RETAINED_IN_TRACK_V1",
            source_file_count=count, source_aggregate_sha256=digest.hexdigest(),
            source_digest_policy="SHA256_CANONICAL_PATH_SIZE_BYTE_SHA256_LINES",
            fact_count=total, monitoring_event_count=len(monitoring),
            first_observed_at=first.observed_at, last_observed_at=last.observed_at,
            first_source_identity=first.source_identity, last_source_identity=last.source_identity,
            first_provider_sequence=first.source_sequence, last_provider_sequence=last.source_sequence,
            unsequenced_fact_count=unsequenced, recovered_fact_count=recovered,
            unordered_fact_count=unordered, observed_low=low, observed_high=high,
            final_observed_price=last.last_price if last_prices_agree else None,
            final_price_disposition="ESTABLISHED" if last_prices_agree else "EQUAL_TIME_ORDER_UNAVAILABLE",
            material_transitions=tuple(_primitive(item) for item in events),
            terminal_event=None if terminal is None else _primitive(terminal),
            final_state=dict(
                track_state=("COMPLETE" if terminal else "MONITORING_INTERRUPTED" if interrupted else "ACTIVE"),
                monitoring_state=("COMPLETE" if terminal else latest_monitor.state.value if latest_monitor else "NOT_ACTIVE"),
                monitoring_reason=None if latest_monitor is None else latest_monitor.reason,
                recovery_disposition="NOT_APPLICABLE_TERMINAL" if terminal else "RECOVERY_REQUIRED",
                entry_state="ENTRY_OBSERVED" if terminal or any(x.outcome is PaperObservationOutcome.ENTRY_OBSERVED for x in events) else "ENTRY_NOT_OBSERVED",
                outcome=terminal.outcome.value if terminal else "OUTCOME_NOT_ESTABLISHED",
            ),
            monitoring_record_identities=tuple(item.record_identity for item in monitoring),
            interruption_count=interruptions, recovery_count=recoveries, monitoring_reason_counts=reasons,
        )
        encoded = _canonical(values)
        integrity = sha256(encoded).hexdigest()
        return PaperObservationHistoricalConsolidationV1(
            "PAPER-OBSERVATION-CONSOLIDATION-" + integrity, integrity, encoded)

    def _historical_selection_path(self, identity):
        return self._track_path(identity).parent / "historical-representation.json"

    def _has_historical_selection(self, identity):
        path = self._historical_selection_path(identity)
        return path.exists() or path.is_symlink()

    def _historical_control_digest(self, identity):
        directory = self._track_path(identity).parent
        digest = sha256()
        paths = [directory / "track.json"]
        for name in ("events", "monitoring"):
            paths.extend((directory / name).glob("*.json"))
        for path in sorted(paths):
            if path.is_symlink():
                raise ValueError("PAPER_HISTORICAL_CONTROL_INVALID")
            encoded = path.read_bytes()
            digest.update(_canonical([str(path.relative_to(directory)), len(encoded),
                                      sha256(encoded).hexdigest()]) + b"\n")
        return digest.hexdigest()

    def publish_historical_consolidation(self, record, *, maintenance_identity, published_at):
        """Explicit maintenance publication; never deletes or grants live authority.

        Caller must hold its authorized reader/writer exclusion boundary. The
        freshly reconstructed record proves exact coverage before pointer-last
        immutable selection. This API is exercised only in fixtures in Slice 6A.
        """
        if (type(record) is not PaperObservationHistoricalConsolidationV1
                or not _identity(maintenance_identity) or not _aware(published_at)):
            raise ValueError("PAPER_HISTORICAL_PUBLICATION_INVALID")
        if (sha256(record.canonical_bytes).hexdigest() != record.integrity_sha256
                or record.identity != "PAPER-OBSERVATION-CONSOLIDATION-" + record.integrity_sha256):
            raise ValueError("PAPER_HISTORICAL_PUBLICATION_INVALID")
        data = json.loads(record.canonical_bytes)
        identity = data["track"]["track_identity"]
        if not re.fullmatch(r"PAPER-OBSERVATION-TRACK-[0-9a-f]{64}", identity):
            raise ValueError("PAPER_HISTORICAL_PUBLICATION_INVALID")
        created_at = datetime.fromisoformat(data["created_at"])
        if published_at < created_at:
            raise ValueError("PAPER_HISTORICAL_PUBLICATION_INVALID")
        pointer = self._historical_selection_path(identity)
        with self._lock:
            if pointer.exists():
                selected = self.load_historical_consolidation(identity)
                if _canonical(selected) != record.canonical_bytes:
                    raise ValueError("PAPER_HISTORICAL_SELECTION_IMMUTABLE")
                return False
            expected = self.prepare_historical_consolidation(identity, created_at=created_at)
            if expected != record:
                raise ValueError("PAPER_HISTORICAL_SOURCE_COVERAGE_MISMATCH")
            # An orphan from an interrupted publication is inert and never
            # selected by readers. Do not overwrite an existing candidate.
            target = pointer.parent / "historical-consolidations" / (record.integrity_sha256 + ".json")
            if target.exists():
                if target.is_symlink() or target.read_bytes() != record.canonical_bytes:
                    raise ValueError("PAPER_HISTORICAL_RECORD_IMMUTABLE")
            else:
                _atomic_encoded(target, record.canonical_bytes)
            values = dict(schema="KRONOS-PAPER-HISTORICAL-SELECTION-V1",
                representation="COMPACT_HISTORICAL", track_identity=identity,
                track_sha256=data["track"]["integrity_sha256"],
                consolidation_identity=record.identity, consolidation_sha256=record.integrity_sha256,
                source_file_count=data["source_file_count"], source_aggregate_sha256=data["source_aggregate_sha256"],
                control_sha256=self._historical_control_digest(identity),
                maintenance_identity=maintenance_identity, published_at=published_at.isoformat(),
                integrity_sha256="")
            values["integrity_sha256"] = _values_digest(values)
            self._append(pointer, {"schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA,
                                   "selection": values}, "PAPER_HISTORICAL_SELECTION_IMMUTABLE")
        return True

    def load_historical_consolidation(self, identity):
        """Validate explicit selection and retained controls, never read raw facts."""
        try:
            pointer = self._historical_selection_path(identity)
            if pointer.is_symlink() or pointer.parent.is_symlink() or self.is_compact(identity):
                raise ValueError
            token = self._file_token(pointer)
            selection = _read(pointer)["selection"]
            if (set(selection) != {"schema", "representation", "track_identity", "track_sha256",
                    "consolidation_identity", "consolidation_sha256", "source_file_count",
                    "source_aggregate_sha256", "control_sha256", "maintenance_identity",
                    "published_at", "integrity_sha256"}
                    or selection["schema"] != "KRONOS-PAPER-HISTORICAL-SELECTION-V1"
                    or selection["representation"] != "COMPACT_HISTORICAL"
                    or selection["track_identity"] != identity
                    or selection["integrity_sha256"] != _values_digest(selection | {"integrity_sha256": ""})
                    or not _digest(selection["consolidation_sha256"])
                    or not _identity(selection["maintenance_identity"])):
                raise ValueError
            path = pointer.parent / "historical-consolidations" / (selection["consolidation_sha256"] + ".json")
            if path.is_symlink() or path.parent.is_symlink():
                raise ValueError
            encoded = path.read_bytes()
            if sha256(encoded).hexdigest() != selection["consolidation_sha256"]:
                raise ValueError
            data = json.loads(encoded)
            track = self.load_track(identity)
            events, monitoring = self.events(identity), self.monitoring(identity)
            first = datetime.fromisoformat(data["first_observed_at"])
            last = datetime.fromisoformat(data["last_observed_at"])
            created = datetime.fromisoformat(data["created_at"])
            published = datetime.fromisoformat(selection["published_at"])
            terminal = events[-1] if events and events[-1].outcome in _TERMINAL_OUTCOMES else None
            final = data["final_state"]
            monitor_state = "COMPLETE" if terminal else monitoring[-1].state.value if monitoring else "NOT_ACTIVE"
            track_state = "COMPLETE" if terminal else "MONITORING_INTERRUPTED" if monitor_state == "INTERRUPTED" else "ACTIVE"
            if (encoded != _canonical(data)
                    or data["schema"] != "KRONOS-PAPER-OBSERVATION-HISTORICAL-CONSOLIDATION-V1"
                    or data["policy"] != "VALIDATED-LEGACY-RESEARCH-CONSOLIDATION-V1"
                    or data["implementation_version"] != "1"
                    or data["authority"] != "RESEARCH_ONLY"
                    or data["currentness"] != "HISTORICAL_NO_CURRENT_APPLICABILITY"
                    or data["monitoring_restorable"] is not False
                    or data["deletion_ready"] is not False
                    or data["deletion_readiness"] != "PENDING_REFERENCE_SCAN"
                    or data["applicability"] is not None
                    or data["track"] != _primitive(track)
                    or selection["track_sha256"] != track.integrity_sha256
                    or selection["consolidation_identity"] != "PAPER-OBSERVATION-CONSOLIDATION-" + selection["consolidation_sha256"]
                    or type(data["fact_count"]) is not int or data["fact_count"] < 1
                    or data["source_file_count"] != 1 + data["fact_count"] + len(events) + len(monitoring)
                    or selection["source_file_count"] != data["source_file_count"]
                    or not _digest(data["source_aggregate_sha256"])
                    or selection["source_aggregate_sha256"] != data["source_aggregate_sha256"]
                    or data["monitoring_event_count"] != len(monitoring)
                    or data["monitoring_record_identities"] != [x.record_identity for x in monitoring]
                    or data["material_transitions"] != [_primitive(x) for x in events]
                    or any(x.track_identity != identity for x in (*events, *monitoring))
                    or data["terminal_event"] != (None if terminal is None else _primitive(terminal))
                    or final["outcome"] != ("OUTCOME_NOT_ESTABLISHED" if terminal is None else terminal.outcome.value)
                    or final["track_state"] != track_state
                    or final["monitoring_state"] != monitor_state
                    or final["monitoring_reason"] != (None if not monitoring else monitoring[-1].reason)
                    or final["recovery_disposition"] != ("RECOVERY_REQUIRED" if terminal is None else "NOT_APPLICABLE_TERMINAL")
                    or final["entry_state"] != ("ENTRY_OBSERVED" if terminal or any(x.outcome is PaperObservationOutcome.ENTRY_OBSERVED for x in events) else "ENTRY_NOT_OBSERVED")
                    or not all(_aware(x) for x in (first, last, created, published))
                    or not first <= last <= created <= published
                    or (pointer.parent / "current-applicability.json").exists()
                    or (pointer.parent / "current-state.json").exists()
                    or self._historical_control_digest(identity) != selection["control_sha256"]
                    or self._file_token(pointer) != token):
                raise ValueError
            return data
        except (OSError, KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError("PAPER_OBSERVATION_HISTORICAL_EVIDENCE_UNAVAILABLE") from error

    def _historical_projection(self, track):
        try:
            data = self.load_historical_consolidation(track.track_identity)
        except ValueError:
            return PaperObservationTrackProjectionV1(track,
                PaperObservationTrackState.MONITORING_INTERRUPTED,
                PaperObservationMonitoringState.INTERRUPTED,
                PaperObservationOutcome.OUTCOME_NOT_ESTABLISHED,
                PaperObservationOutcome.OUTCOME_NOT_ESTABLISHED,
                PaperObservationOutcome.OUTCOME_NOT_ESTABLISHED, (), track.created_at, None,
                "RECOVERY_REQUIRED", history_representation="HISTORY_UNAVAILABLE",
                raw_detail_availability="HISTORICAL_DETAIL_UNAVAILABLE",
                historical_detail_reason="PAPER_OBSERVATION_HISTORICAL_EVIDENCE_UNAVAILABLE")
        final = data["final_state"]
        boundaries = [datetime.fromisoformat(x["observed_at"]) for x in data["material_transitions"]]
        return PaperObservationTrackProjectionV1(track,
            PaperObservationTrackState(final["track_state"]),
            PaperObservationMonitoringState(final["monitoring_state"]),
            PaperObservationOutcome(final["entry_state"]),
            PaperObservationOutcome(data["material_transitions"][-1]["outcome"] if boundaries else "ENTRY_NOT_OBSERVED"),
            PaperObservationOutcome(final["outcome"]),
            tuple(x["event_identity"] for x in data["material_transitions"]), track.created_at,
            max([datetime.fromisoformat(data["last_observed_at"]), *boundaries]),
            final["recovery_disposition"], history_representation="COMPACT_HISTORICAL",
            raw_detail_availability="HISTORICAL_DETAIL_UNAVAILABLE",
            first_factual_observation_at=min([datetime.fromisoformat(data["first_observed_at"]), *boundaries]),
            historical_fact_count=data["fact_count"], historical_source_count=data["source_file_count"],
            historical_source_sha256=data["source_aggregate_sha256"],
            historical_consolidation_identity="PAPER-OBSERVATION-CONSOLIDATION-" + sha256(_canonical(data)).hexdigest(),
            historical_detail_reason="COMPACT_SUMMARY_ONLY_RAW_FACTS_NOT_REVALIDATED")

    def initialize_compact(self, state):
        path = self.root / state.track_identity / "current-state.json"
        self._append(path, {"schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA,
                           "checkpoint": _primitive(state)},
                     "PAPER_OBSERVATION_COMPACT_ADMISSION_CONFLICT")

    @staticmethod
    def _file_token(path):
        stat = path.stat()
        return stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    def load_compact(self, track_identity):
        """Read one checkpoint, its exact head, and current authority; never scan."""
        path = self.root / track_identity / "current-state.json"
        pointer = self._current_applicability_path(track_identity)
        try:
            tokens = self._file_token(path), self._file_token(pointer), self._file_token(self._track_path(track_identity))
            state = _compact_from_dict(_read(path)["checkpoint"])
            track = self.load_track(track_identity)
            applicable = self.current_applicability(track_identity)
            bound = applicable
            if (applicable is not None and applicable.state is not PaperObservationMonitoringApplicabilityState.OPEN):
                if applicable.predecessor_applicability_identity != state.applicability_identity:
                    predecessor = self._load_applicability_record(track_identity,
                        applicable.predecessor_applicability_identity)
                    if (applicable.state is not PaperObservationMonitoringApplicabilityState.CLOSED
                            or predecessor.state is not PaperObservationMonitoringApplicabilityState.SUSPENDED
                            or predecessor.predecessor_applicability_identity != state.applicability_identity
                            or predecessor.authority != state.authority):
                        raise ValueError
                bound = self._load_applicability_record(track_identity, state.applicability_identity)
            if (state.track_identity != track_identity or state.track_sha256 != track.integrity_sha256
                    or bound is None or state.applicability_identity != bound.record_identity
                    or state.applicability_sha256 != bound.integrity_sha256
                    or state.authority != applicable.authority
                    or (state.entry, state.stop, state.target) != (track.observation_entry_reference, track.stop, track.target)
                    or state.decision_identity != track.sponsor_decision_identity):
                raise ValueError
            if state.material_head is not None:
                transition = _read(self.root / track_identity / "transitions" / f"{state.material_head}.json")["transition"]
                if (sha256(_canonical(transition)).hexdigest() != state.material_head
                        or transition["track_identity"] != track_identity
                        or transition["kind"] not in COMPACT_TRANSITIONS):
                    raise ValueError
                if transition["applicability_identity"] != state.applicability_identity:
                    head_binding = self._load_applicability_record(track_identity, transition["applicability_identity"])
                    if head_binding.authority != state.authority:
                        raise ValueError
            if tokens != (self._file_token(path), self._file_token(pointer), self._file_token(self._track_path(track_identity))):
                raise ValueError
            self._compact_tokens[track_identity] = (state.integrity_sha256, tokens)
            if applicable.state is PaperObservationMonitoringApplicabilityState.OPEN:
                self._compact_open.add(track_identity)
            else:
                self._compact_open.discard(track_identity)
            return state
        except (OSError, KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError("PAPER_OBSERVATION_COMPACT_RECOVERY_REQUIRED") from error

    def prepare_compact(self, old, new, kind=None):
        """Prepare serialized immutable transition and checkpoint outside locks."""
        transition = None
        if kind is not None:
            if kind not in COMPACT_TRANSITIONS:
                raise ValueError("PAPER_OBSERVATION_COMPACT_TRANSITION_INVALID")
            transition = dict(track_identity=new.track_identity,
                applicability_identity=new.applicability_identity, kind=kind,
                predecessor_checkpoint=old.integrity_sha256,
                predecessor_transition=old.material_head,
                outcome=new.outcome.value, entry_at=_primitive(new.entry_at),
                stop_at=_primitive(new.stop_at), target_at=_primitive(new.target_at),
                observation_sha256=new.observation_sha256,
                reconciliation=new.latest_reconciliation,
                monitoring_reason=new.monitoring_reason)
            head = sha256(_canonical(transition)).hexdigest()
            new = compact_replace(new, material_head=head,
                material_count=old.material_count + 1,
                latest_gap_identity=head if kind == "GAP_BEGAN" else new.latest_gap_identity)
            new = replace(new, predecessor_sha256=old.integrity_sha256,
                integrity_sha256=_values_digest({**_primitive(new), "predecessor_sha256": old.integrity_sha256, "integrity_sha256": ""}))
        new = replace(new, predecessor_sha256=old.integrity_sha256,
            integrity_sha256=_values_digest({**_primitive(new), "predecessor_sha256": old.integrity_sha256, "integrity_sha256": ""}))
        encoded = _canonical({"schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA,
                              "checkpoint": _primitive(new)}) + b"\n"
        transition_bytes = None if transition is None else _canonical({
            "schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA, "transition": transition}) + b"\n"
        return new, transition_bytes, encoded

    def _retain_compact_transition(self, path, encoded):
        # Bytes and integrity were prepared before publication coordination.
        if path.exists():
            if path.read_bytes() != encoded:
                raise ValueError("PAPER_OBSERVATION_COMPACT_TRANSITION_CONFLICT")
            return
        _atomic_encoded(path, encoded)

    def publish_compact(self, old, prepared):
        new, transition, encoded = prepared
        path = self.root / old.track_identity / "current-state.json"
        pointer = self._current_applicability_path(old.track_identity)
        with self._lock:
            expected = self._compact_tokens.get(old.track_identity)
            if expected != (old.integrity_sha256,
                    (self._file_token(path), self._file_token(pointer), self._file_token(self._track_path(old.track_identity)))):
                raise ValueError("PAPER_OBSERVATION_COMPACT_AUTHORITY_STALE")
            if transition is not None:
                self._retain_compact_transition(
                    self.root / old.track_identity / "transitions" / f"{new.material_head}.json", transition)
            _atomic_encoded(path, encoded)
            self._compact_tokens[old.track_identity] = (new.integrity_sha256,
                (self._file_token(path), self._file_token(pointer), self._file_token(self._track_path(old.track_identity))))
        return new

    def retain_track(self, track: PaperObservationTrackV1, *, compact=False) -> PaperObservationTrackV1:
        if type(track) is not PaperObservationTrackV1:
            raise TypeError("PAPER_OBSERVATION_TRACK_INVALID")
        path = self._track_path(track.track_identity)
        payload = {"schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA, "track": _primitive(track)}
        if compact:
            payload["storage_generation"] = COMPACT_SCHEMA
        with self._lock:
            if path.exists():
                restored = self.load_track(track.track_identity)
                if restored != track:
                    raise ValueError("PAPER_OBSERVATION_TRACK_IMMUTABILITY_VIOLATION")
                return restored
            _atomic(path, payload)
        return track

    def append_fact(self, fact: PaperObservationMarketFactV1) -> bool:
        if self._has_historical_selection(fact.track_identity):
            raise ValueError("PAPER_OBSERVATION_HISTORICAL_DETAIL_UNAVAILABLE")
        return self._append(
            self.root / fact.track_identity / "facts" / f"{fact.fact_identity}.json",
            {"schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA, "fact": _primitive(fact)},
            "PAPER_OBSERVATION_FACT_IMMUTABILITY_VIOLATION",
        )

    def append_event(self, event: PaperObservationEventV1) -> bool:
        existing = self.events(event.track_identity)
        if event.outcome in _TERMINAL_OUTCOMES:
            if not any(
                item.outcome is PaperObservationOutcome.ENTRY_OBSERVED
                for item in existing
            ):
                raise ValueError("PAPER_OBSERVATION_TERMINAL_BEFORE_ENTRY")
            if any(item.outcome in _TERMINAL_OUTCOMES for item in existing):
                duplicate = next(
                    (item for item in existing if item.event_identity == event.event_identity),
                    None,
                )
                if duplicate == event:
                    return False
                raise ValueError("PAPER_OBSERVATION_TERMINAL_OUTCOME_IMMUTABLE")
        return self._append(
            self.root / event.track_identity / "events" / f"{event.event_identity}.json",
            {"schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA, "event": _primitive(event)},
            "PAPER_OBSERVATION_EVENT_IMMUTABILITY_VIOLATION",
        )

    def append_monitoring(self, record: PaperObservationMonitoringRecordV1) -> bool:
        return self._append(
            self.root / record.track_identity / "monitoring" / f"{record.record_identity}.json",
            {"schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA, "monitoring": _primitive(record)},
            "PAPER_OBSERVATION_MONITORING_IMMUTABILITY_VIOLATION",
        )

    def append_applicability(
        self, record: PaperObservationMonitoringApplicabilityV1
    ) -> bool:
        if self._has_historical_selection(record.track_identity):
            raise ValueError("PAPER_HISTORICAL_MONITORING_AUTHORITY_PROHIBITED")
        track = self.load_track(record.track_identity)
        if (
            record.authority.sponsor_decision_identity
            != track.sponsor_decision_identity
            or record.authority.native_assessment_sha256
            != track.native_assessment_sha256
            or record.authority.direction is not track.direction
            or record.authority.geometry_identity
            != track.step31_observation_identity
            or record.authority.geometry_sha256
            != track.step31_observation_sha256
            or record.authority.canonical_instrument != track.canonical_instrument
        ):
            raise ValueError("PAPER_OBSERVATION_APPLICABILITY_BINDING_INVALID")
        return self._append(
            self.root
            / record.track_identity
            / "applicability"
            / f"{record.record_identity}.json",
            {
                "schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA,
                "applicability": _primitive(record),
            },
            "PAPER_OBSERVATION_APPLICABILITY_IMMUTABILITY_VIOLATION",
        )

    def publish_current_applicability(
        self, record: PaperObservationMonitoringApplicabilityV1
    ) -> bool:
        """Publish one already-retained generation with the pointer written last."""

        retained = self._load_applicability_record(
            record.track_identity, record.record_identity
        )
        if retained != record:
            raise ValueError("PAPER_OBSERVATION_APPLICABILITY_BINDING_INVALID")
        path = self._current_applicability_path(record.track_identity)
        payload = {
            "schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA,
            "current_applicability": {
                "track_identity": record.track_identity,
                "record_identity": record.record_identity,
                "record_sha256": record.integrity_sha256,
            },
        }
        with self._lock:
            if path.exists():
                if _read(path) == payload:
                    return False
                raise ValueError("PAPER_OBSERVATION_APPLICABILITY_CURRENT_CONFLICT")
            _atomic(path, payload)
        return True

    def current_applicability(
        self, track_identity: str
    ) -> PaperObservationMonitoringApplicabilityV1 | None:
        path = self._current_applicability_path(track_identity)
        if not path.exists():
            return None
        try:
            pointer = _read(path)["current_applicability"]
            if (
                type(pointer) is not dict
                or pointer.get("track_identity") != track_identity
                or not _identity(pointer.get("record_identity"))
                or not _digest(pointer.get("record_sha256"))
            ):
                raise ValueError
            record = self._load_applicability_record(
                track_identity, str(pointer["record_identity"])
            )
            if record.integrity_sha256 != pointer["record_sha256"]:
                raise ValueError
            return record
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID") from error

    def prepare_applicability_transition(self, previous, record):
        """Prepared exact successor; pointer CAS does not parse under the lock."""
        if (previous.state is PaperObservationMonitoringApplicabilityState.CLOSED
                or record.track_identity != previous.track_identity
                or record.predecessor_applicability_identity != previous.record_identity
                or record.authority != previous.authority):
            raise ValueError("PAPER_OBSERVATION_APPLICABILITY_TRANSITION_INVALID")
        path = self._current_applicability_path(previous.track_identity)
        token = self._file_token(path)
        if self.current_applicability(previous.track_identity) != previous:
            raise ValueError("PAPER_OBSERVATION_APPLICABILITY_STALE")
        encoded_record = _canonical({"schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA,
                                    "applicability": _primitive(record)}) + b"\n"
        encoded_pointer = _canonical({"schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA,
            "current_applicability": dict(track_identity=record.track_identity,
                record_identity=record.record_identity, record_sha256=record.integrity_sha256)}) + b"\n"
        record_path = self.root / record.track_identity / "applicability" / f"{record.record_identity}.json"
        return path, token, record_path, encoded_record, encoded_pointer

    def publish_applicability_transition(self, prepared):
        path, token, record_path, encoded_record, encoded_pointer = prepared
        with self._lock:
            if self._file_token(path) != token:
                raise ValueError("PAPER_OBSERVATION_APPLICABILITY_STALE")
            self._retain_compact_transition(record_path, encoded_record)
            _atomic_encoded(path, encoded_pointer)
            self._compact_open.discard(path.parent.name)

    def publish_compact_resumption(self, old, checkpoint, applicability):
        new, transition, encoded = checkpoint
        path, token, record_path, record_bytes, pointer_bytes = applicability
        current = self.root / old.track_identity / 'current-state.json'
        track = self._track_path(old.track_identity)
        with self._lock:
            if (transition is not None or self._file_token(path) != token
                    or self._compact_tokens.get(old.track_identity) != (old.integrity_sha256,
                        (self._file_token(current), token, self._file_token(track)))):
                raise ValueError('PAPER_OBSERVATION_COMPACT_AUTHORITY_STALE')
            self._retain_compact_transition(record_path, record_bytes)
            _atomic_encoded(current, encoded)
            _atomic_encoded(path, pointer_bytes)
            self._compact_tokens[old.track_identity] = (new.integrity_sha256,
                (self._file_token(current), self._file_token(path), self._file_token(track)))
            self._compact_open.add(old.track_identity)
        return new

    def _load_applicability_record(
        self, track_identity: str, record_identity: str
    ) -> PaperObservationMonitoringApplicabilityV1:
        payload = _read(
            self.root
            / track_identity
            / "applicability"
            / f"{record_identity}.json"
        )
        record = _applicability_from_dict(payload["applicability"])
        if record.track_identity != track_identity:
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID")
        return record

    def load_track(self, track_identity: str) -> PaperObservationTrackV1:
        try:
            payload = _read(self._track_path(track_identity))
            return _track_from_dict(payload["track"])
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID") from error

    def load_all_tracks(self) -> tuple[PaperObservationTrackV1, ...]:
        return tuple(
            self.load_track(path.parent.name)
            for path in sorted(self.root.glob("PAPER-OBSERVATION-TRACK-*/track.json"))
        )

    def events(self, track_identity: str) -> tuple[PaperObservationEventV1, ...]:
        try:
            records = tuple(
                _event_from_dict(_read(path)["event"])
                for path in sorted((self.root / track_identity / "events").glob("*.json"))
            )
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID") from error
        order = {
            PaperObservationOutcome.ENTRY_OBSERVED: 0,
            PaperObservationOutcome.STOP_LEVEL_TOUCHED: 1,
            PaperObservationOutcome.TARGET_LEVEL_TOUCHED: 1,
            PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED: 1,
            PaperObservationOutcome.OUTCOME_NOT_ESTABLISHED: 2,
        }
        return tuple(sorted(
            records,
            key=lambda item: (
                item.observed_at,
                item.recorded_at,
                order[item.outcome],
                item.event_identity,
            ),
        ))

    def facts(self, track_identity: str) -> tuple[PaperObservationMarketFactV1, ...]:
        if self._has_historical_selection(track_identity):
            self.load_historical_consolidation(track_identity)
            raise ValueError("PAPER_OBSERVATION_HISTORICAL_DETAIL_UNAVAILABLE")
        try:
            records = tuple(
                self._load_fact(path)
                for path in sorted((self.root / track_identity / "facts").glob("*.json"))
            )
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID") from error
        return tuple(sorted(records, key=lambda item: (item.observed_at, item.fact_identity)))

    def _load_fact(self, path: Path) -> PaperObservationMarketFactV1:
        try:
            encoded = path.read_bytes()
        except OSError as error:
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID") from error
        token = (PAPER_OBSERVATION_TRACK_STORE_SCHEMA,
                 PAPER_OBSERVATION_TRACK_CONTRACT_VERSION,
                 PAPER_OBSERVATION_TRACK_POLICY_VERSION,
                 PaperObservationMarketFactV1, PaperObservationMarketFactV1.__post_init__,
                 _fact_from_bytes, _fact_from_dict, _record_digest, _primitive)
        return self._validated_facts.load(path, encoded, token, _fact_from_bytes)

    def monitoring(
        self, track_identity: str
    ) -> tuple[PaperObservationMonitoringRecordV1, ...]:
        try:
            records = tuple(
                _monitoring_from_dict(_read(path)["monitoring"])
                for path in sorted((self.root / track_identity / "monitoring").glob("*.json"))
            )
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID") from error
        return tuple(sorted(records, key=lambda item: (item.recorded_at, item.record_identity)))

    def applicability(
        self, track_identity: str
    ) -> tuple[PaperObservationMonitoringApplicabilityV1, ...]:
        try:
            records = tuple(
                _applicability_from_dict(_read(path)["applicability"])
                for path in sorted(
                    (self.root / track_identity / "applicability").glob("*.json")
                )
            )
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID") from error
        if any(item.track_identity != track_identity for item in records):
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID")
        return tuple(
            sorted(records, key=lambda item: (item.recorded_at, item.record_identity))
        )

    def projection(self, track_identity: str) -> PaperObservationTrackProjectionV1:
        track = self.load_track(track_identity)
        if self._has_historical_selection(track_identity):
            return self._historical_projection(track)
        events = self.events(track_identity)
        facts = self.facts(track_identity)
        monitoring = self.monitoring(track_identity)
        # Explicit full projection still reads and validates every retained fact,
        # event and monitoring record above. Prospective current truth comes
        # from its separately validated checkpoint after that full validation.
        if self.is_compact(track_identity):
            return compact_projection(track, self.load_compact(track_identity))
        latest_outcome = (
            PaperObservationOutcome.ENTRY_NOT_OBSERVED
            if not events else events[-1].outcome
        )
        entry_seen = any(item.outcome is PaperObservationOutcome.ENTRY_OBSERVED for item in events)
        if latest_outcome in _TERMINAL_OUTCOMES:
            state = PaperObservationTrackState.COMPLETE
            monitor_state = PaperObservationMonitoringState.COMPLETE
        else:
            monitor_state = (
                PaperObservationMonitoringState.NOT_ACTIVE
                if not monitoring else monitoring[-1].state
            )
            state = (
                PaperObservationTrackState.MONITORING_INTERRUPTED
                if monitor_state is PaperObservationMonitoringState.INTERRUPTED
                else PaperObservationTrackState.ACTIVE
            )
        return PaperObservationTrackProjectionV1(
            track=track,
            track_state=state,
            monitoring_state=monitor_state,
            entry_state=(
                PaperObservationOutcome.ENTRY_OBSERVED
                if entry_seen or latest_outcome in _TERMINAL_OUTCOMES
                else PaperObservationOutcome.ENTRY_NOT_OBSERVED
            ),
            latest_event=latest_outcome,
            outcome_state=latest_outcome,
            event_identities=tuple(item.event_identity for item in events),
            created_at=track.created_at,
            last_factual_observation_at=(
                None if not facts and not events else max(
                    tuple(item.observed_at for item in facts)
                    + tuple(item.observed_at for item in events)
                )
            ),
            monitoring_reason=(
                "MONITORING_CAPABILITY_NOT_YET_REGISTERED"
                if not monitoring else monitoring[-1].reason
            ),
            raw_detail_availability="RAW_RECORDS_VALIDATED" if facts else "HISTORICAL_DETAIL_UNAVAILABLE",
            first_factual_observation_at=None if not facts else facts[0].observed_at,
            historical_fact_count=len(facts) if facts else None,
            historical_detail_reason=None if facts else "NO_RETAINED_RAW_FACTS_NO_COMPACT_SELECTION",
        )

    def restoration_projection(
        self,
        track_identity: str,
        current_authority: PaperObservationMonitoringAuthorityV1 | None = None,
    ) -> PaperObservationRestorationProjectionV1:
        """Project monitoring authority without touching historical market facts."""

        track = self.load_track(track_identity)
        if self.is_compact(track_identity):
            return self.compact_restoration_projection(track, current_authority)
        events = self.events(track_identity)
        monitoring = self.monitoring(track_identity)
        applicability_corrupt = False
        try:
            applicability = self.current_applicability(track_identity)
        except ValueError:
            applicability = None
            applicability_corrupt = True
        if any(item.track_identity != track.track_identity for item in events) or any(
            item.track_identity != track.track_identity for item in monitoring
        ):
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID")
        entry_seen = False
        terminal_seen = False
        for event in events:
            if event.outcome is PaperObservationOutcome.ENTRY_OBSERVED:
                if terminal_seen:
                    raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID")
                entry_seen = True
            elif event.outcome in _TERMINAL_OUTCOMES:
                if not entry_seen or terminal_seen:
                    raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID")
                terminal_seen = True
        latest_event = (
            PaperObservationOutcome.ENTRY_NOT_OBSERVED
            if not events
            else events[-1].outcome
        )
        latest_monitoring = None if not monitoring else monitoring[-1]
        return PaperObservationRestorationProjectionV1(
            track_identity=track.track_identity,
            canonical_instrument=track.canonical_instrument,
            track_authority=track.authority,
            track_integrity_sha256=track.integrity_sha256,
            sponsor_decision_identity=track.sponsor_decision_identity,
            decision_snapshot_identity=track.decision_snapshot_identity,
            native_run_identity=track.native_run_identity,
            terminal=latest_event in _TERMINAL_OUTCOMES,
            latest_event=latest_event,
            latest_event_identity=(
                None if not events else events[-1].event_identity
            ),
            monitoring_state=(
                PaperObservationMonitoringState.NOT_ACTIVE
                if latest_monitoring is None
                else latest_monitoring.state
            ),
            monitoring_reason=(
                "MONITORING_CAPABILITY_NOT_YET_REGISTERED"
                if latest_monitoring is None
                else latest_monitoring.reason
            ),
            monitoring_record_identity=(
                None if latest_monitoring is None else latest_monitoring.record_identity
            ),
            applicability=(
                PaperObservationMonitoringApplicabilityProjectionV1(
                    state=PaperObservationMonitoringApplicabilityState.SUSPENDED,
                    operation="RECOVERY_REQUIRED",
                    automatic_restoration=False,
                    reason_codes=("APPLICABILITY_RECORD_CORRUPT",),
                    record_identity=None,
                )
                if applicability_corrupt
                else project_monitoring_applicability(
                    applicability,
                    current_authority,
                )
            ),
        )

    def compact_restoration_projection(self, track, current_authority, *, continuity_proven=False):
        """Separate operational projection; full historical projection is unchanged."""
        try:
            state = self.load_compact(track.track_identity)
            applicability = project_monitoring_applicability(
                self.current_applicability(track.track_identity), current_authority)
            # A continuity gap cannot turn explicit CLOSED authority into a
            # recoverable owner. A retained gap proof may admit a new generation.
            if (applicability.operation != "MONITORING_CLOSED" and not state.terminal and (
                    state.monitoring_state is PaperObservationMonitoringState.INTERRUPTED
                    or (state.latest_observation is not None
                        and not (continuity_proven or state.resume_after_gap)))):
                applicability = PaperObservationMonitoringApplicabilityProjectionV1(
                    PaperObservationMonitoringApplicabilityState.SUSPENDED,
                    "RECOVERY_REQUIRED", False,
                    (state.monitoring_reason if state.monitoring_state is PaperObservationMonitoringState.INTERRUPTED
                     else "COMPACT_CONTINUITY_RECOVERY_REQUIRED",), state.applicability_identity)
        except ValueError:
            state = None
            applicability = PaperObservationMonitoringApplicabilityProjectionV1(
                PaperObservationMonitoringApplicabilityState.SUSPENDED,
                "RECOVERY_REQUIRED", False, ("COMPACT_CHECKPOINT_RECOVERY_REQUIRED",), None)
        return PaperObservationRestorationProjectionV1(
            track.track_identity, track.canonical_instrument, track.authority,
            track.integrity_sha256, track.sponsor_decision_identity,
            track.decision_snapshot_identity, track.native_run_identity,
            False if state is None else state.terminal,
            PaperObservationOutcome.ENTRY_NOT_OBSERVED if state is None else state.outcome,
            None if state is None else state.material_head,
            PaperObservationMonitoringState.INTERRUPTED if state is None else state.monitoring_state,
            "COMPACT_CHECKPOINT_RECOVERY_REQUIRED" if state is None else state.monitoring_reason,
            None if state is None else state.material_head, applicability,
        )

    def restoration_projections(
        self,
        current_authority_resolver: (
            Callable[[PaperObservationTrackV1], PaperObservationMonitoringAuthorityV1 | None]
            | None
        ) = None,
    ) -> tuple[PaperObservationRestorationProjectionV1, ...]:
        values = []
        for track in self.load_all_tracks():
            baseline = self.restoration_projection(track.track_identity)
            if baseline.terminal or current_authority_resolver is None:
                values.append(baseline)
                continue
            current = current_authority_resolver(track)
            if current is not None and type(current) is not PaperObservationMonitoringAuthorityV1:
                raise TypeError("PAPER_OBSERVATION_CURRENT_AUTHORITY_INVALID")
            values.append(self.restoration_projection(track.track_identity, current))
        return tuple(values)

    def _append(self, path: Path, payload: dict[str, object], code: str) -> bool:
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError(code)
                return False
            _atomic(path, payload)
        return True

    def _track_path(self, track_identity: str) -> Path:
        if not _identity(track_identity):
            raise ValueError("PAPER_OBSERVATION_TRACK_IDENTITY_INVALID")
        return self.root / track_identity / "track.json"

    def _current_applicability_path(self, track_identity: str) -> Path:
        if not _identity(track_identity):
            raise ValueError("PAPER_OBSERVATION_TRACK_IDENTITY_INVALID")
        return self.root / track_identity / "current-applicability.json"


def make_market_fact(
    track: PaperObservationTrackV1,
    *,
    last_price: Decimal,
    observed_at: datetime,
    received_at: datetime,
    source_identity: str,
    source_sequence: int | None,
    ordering_deterministic: bool,
    recovered: bool,
) -> PaperObservationMarketFactV1:
    identity = "PAPER-OBSERVATION-FACT-" + sha256(
        f"{track.track_identity}:{source_identity}:{observed_at.isoformat()}:{last_price}".encode()
    ).hexdigest()
    values = dict(
        fact_identity=identity,
        track_identity=track.track_identity,
        canonical_instrument=track.canonical_instrument,
        last_price=Decimal(last_price),
        observed_at=observed_at,
        received_at=received_at,
        source_identity=source_identity,
        source_sequence=source_sequence,
        ordering_deterministic=ordering_deterministic,
        recovered=recovered,
        integrity_sha256="",
    )
    return PaperObservationMarketFactV1(**(
        values | {"integrity_sha256": _values_digest(values)}
    ))


def make_event(
    track: PaperObservationTrackV1,
    outcome: PaperObservationOutcome,
    *,
    observed_at: datetime,
    recorded_at: datetime,
    source_identity: str,
    source_kind: PaperObservationSourceKind,
    observed_price: Decimal | None = None,
    interval_low: Decimal | None = None,
    interval_high: Decimal | None = None,
) -> PaperObservationEventV1:
    identity = "PAPER-OBSERVATION-EVENT-" + sha256(
        (
            f"{track.track_identity}:{outcome.value}:{source_identity}:"
            f"{observed_at.isoformat()}:{observed_price}:{interval_low}:{interval_high}"
        ).encode()
    ).hexdigest()
    values = dict(
        event_identity=identity,
        track_identity=track.track_identity,
        outcome=outcome,
        observed_at=observed_at,
        recorded_at=recorded_at,
        source_identity=source_identity,
        source_kind=source_kind,
        observed_price=observed_price,
        interval_low=interval_low,
        interval_high=interval_high,
        integrity_sha256="",
    )
    return PaperObservationEventV1(**(
        values | {"integrity_sha256": _values_digest(values)}
    ))


def make_monitoring_record(
    track_identity: str,
    state: PaperObservationMonitoringState,
    reason: str,
    recorded_at: datetime,
) -> PaperObservationMonitoringRecordV1:
    identity = "PAPER-OBSERVATION-MONITORING-" + sha256(
        f"{track_identity}:{state.value}:{reason}:{recorded_at.isoformat()}".encode()
    ).hexdigest()
    values = dict(
        record_identity=identity,
        track_identity=track_identity,
        state=state,
        reason=reason,
        recorded_at=recorded_at,
        integrity_sha256="",
    )
    return PaperObservationMonitoringRecordV1(**(
        values | {"integrity_sha256": _values_digest(values)}
    ))


def _track_from_dict(value: dict[str, object]) -> PaperObservationTrackV1:
    data = dict(value)
    for name in ("observation_entry_reference", "stop", "target", "invalidation"):
        data[name] = None if data[name] is None else Decimal(str(data[name]))
    for name in ("risk_distance", "reward_distance", "risk_reward_ratio"):
        data[name] = None if data[name] is None else Decimal(str(data[name]))
    data["direction"] = V1Direction(data["direction"])
    data["step31_severity"] = Step31WarningSeverity(data["step31_severity"])
    data["step31_warnings"] = tuple(data["step31_warnings"])
    data["activation_disposition"] = SponsorActivationDisposition(data["activation_disposition"])
    data["created_at"] = datetime.fromisoformat(str(data["created_at"]))
    data["sponsor_decision_timestamp"] = datetime.fromisoformat(
        str(data["sponsor_decision_timestamp"])
    )
    data["provenance"] = tuple(data["provenance"])
    return PaperObservationTrackV1(**data)


def _fact_from_bytes(encoded: bytes) -> PaperObservationMarketFactV1:
    payload = json.loads(encoded.decode("utf-8"))
    if type(payload) is not dict or payload.get("schema") != PAPER_OBSERVATION_TRACK_STORE_SCHEMA:
        raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID")
    return _fact_from_dict(payload["fact"])


def _fact_from_dict(value: dict[str, object]) -> PaperObservationMarketFactV1:
    data = dict(value)
    data["last_price"] = Decimal(str(data["last_price"]))
    data["observed_at"] = datetime.fromisoformat(str(data["observed_at"]))
    data["received_at"] = datetime.fromisoformat(str(data["received_at"]))
    return PaperObservationMarketFactV1(**data)


def _event_from_dict(value: dict[str, object]) -> PaperObservationEventV1:
    data = dict(value)
    data["outcome"] = PaperObservationOutcome(data["outcome"])
    data["source_kind"] = PaperObservationSourceKind(data["source_kind"])
    for name in ("observed_price", "interval_low", "interval_high"):
        data[name] = None if data[name] is None else Decimal(str(data[name]))
    data["observed_at"] = datetime.fromisoformat(str(data["observed_at"]))
    data["recorded_at"] = datetime.fromisoformat(str(data["recorded_at"]))
    return PaperObservationEventV1(**data)


def _monitoring_from_dict(
    value: dict[str, object]
) -> PaperObservationMonitoringRecordV1:
    data = dict(value)
    data["state"] = PaperObservationMonitoringState(data["state"])
    data["recorded_at"] = datetime.fromisoformat(str(data["recorded_at"]))
    return PaperObservationMonitoringRecordV1(**data)


def _applicability_from_dict(
    value: dict[str, object]
) -> PaperObservationMonitoringApplicabilityV1:
    data = dict(value)
    data["state"] = PaperObservationMonitoringApplicabilityState(data["state"])
    authority = dict(data["authority"])
    authority["direction"] = V1Direction(authority["direction"])
    authority["capability_requirements"] = tuple(authority["capability_requirements"])
    data["authority"] = PaperObservationMonitoringAuthorityV1(**authority)
    data["recorded_at"] = datetime.fromisoformat(str(data["recorded_at"]))
    return PaperObservationMonitoringApplicabilityV1(**data)


def _read(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            type(payload) is not dict
            or payload.get("schema") != PAPER_OBSERVATION_TRACK_STORE_SCHEMA
        ):
            raise ValueError
        return payload
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID") from error


def _atomic(path: Path, payload: dict[str, object]) -> None:
    _atomic_encoded(path, _canonical(payload) + b"\n")


def _atomic_encoded(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _record_digest(record: object) -> str:
    values = _primitive(record)
    values["integrity_sha256"] = ""
    return sha256(_canonical(values)).hexdigest()


def _values_digest(values: dict[str, object]) -> str:
    return sha256(_canonical(values)).hexdigest()


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(_primitive(value), sort_keys=True, separators=(",", ":")).encode()


def _identity(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _instrument(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Z0-9&._ -]{1,64}", value) is not None


def _digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _finite(value: object) -> bool:
    return type(value) is Decimal and value.is_finite()


__all__ = [
    "LocalPaperObservationTrackStore",
    "PAPER_OBSERVATION_TRACK_AUTHORITY",
    "PAPER_OBSERVATION_TRACK_CONTRACT_ID",
    "PAPER_OBSERVATION_TRACK_CONTRACT_VERSION",
    "PAPER_OBSERVATION_TRACK_POLICY_ID",
    "PAPER_OBSERVATION_MONITORING_APPLICABILITY_CONTRACT_ID",
    "PAPER_OBSERVATION_MONITORING_APPLICABILITY_CONTRACT_VERSION",
    "PAPER_OBSERVATION_RETAINED_MATERIAL_TRANSITIONS",
    "PaperObservationEventV1",
    "PaperObservationMarketFactV1",
    "PaperObservationMonitoringRecordV1",
    "PaperObservationMonitoringApplicabilityProjectionV1",
    "PaperObservationMonitoringApplicabilityState",
    "PaperObservationMonitoringApplicabilityV1",
    "PaperObservationMonitoringAuthorityV1",
    "PaperObservationMonitoringState",
    "PaperObservationOutcome",
    "PaperObservationRestorationProjectionV1",
    "PaperObservationSourceKind",
    "PaperObservationTrackProjectionV1",
    "PaperObservationTrackState",
    "PaperObservationTrackV1",
    "create_paper_observation_track",
    "make_event",
    "make_market_fact",
    "make_monitoring_record",
    "make_monitoring_applicability",
    "project_monitoring_applicability",
]
