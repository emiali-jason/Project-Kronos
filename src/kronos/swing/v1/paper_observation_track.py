"""Non-position PAPER market-path evidence governed by ADR-0016.

This module owns immutable research evidence only.  It creates no Sponsor
Position, objective model, Risk permission, fill, P&L, actual R, order, or
broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorActivationDisposition,
    SponsorObservationDecisionResult,
)
from kronos.swing.v1.step31_observation import (
    STEP31_OBSERVATION_CONTRACT_ID,
    STEP31_OBSERVATION_CONTRACT_VERSION,
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
            or self.step31_contract_identity != STEP31_OBSERVATION_CONTRACT_ID
            or self.step31_contract_version != STEP31_OBSERVATION_CONTRACT_VERSION
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


class LocalPaperObservationTrackStore:
    """Append-only Track, factual-observation, event, and transport evidence."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("PAPER_OBSERVATION_STORE_INVALID")
        self._lock = RLock()

    def retain_track(self, track: PaperObservationTrackV1) -> PaperObservationTrackV1:
        if type(track) is not PaperObservationTrackV1:
            raise TypeError("PAPER_OBSERVATION_TRACK_INVALID")
        path = self._track_path(track.track_identity)
        payload = {"schema": PAPER_OBSERVATION_TRACK_STORE_SCHEMA, "track": _primitive(track)}
        with self._lock:
            if path.exists():
                restored = self.load_track(track.track_identity)
                if restored != track:
                    raise ValueError("PAPER_OBSERVATION_TRACK_IMMUTABILITY_VIOLATION")
                return restored
            _atomic(path, payload)
        return track

    def append_fact(self, fact: PaperObservationMarketFactV1) -> bool:
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
        try:
            records = tuple(
                _fact_from_dict(_read(path)["fact"])
                for path in sorted((self.root / track_identity / "facts").glob("*.json"))
            )
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError("PAPER_OBSERVATION_STORED_RECORD_INVALID") from error
        return tuple(sorted(records, key=lambda item: (item.observed_at, item.fact_identity)))

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

    def projection(self, track_identity: str) -> PaperObservationTrackProjectionV1:
        track = self.load_track(track_identity)
        events = self.events(track_identity)
        facts = self.facts(track_identity)
        monitoring = self.monitoring(track_identity)
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
        )

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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
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
    "PaperObservationEventV1",
    "PaperObservationMarketFactV1",
    "PaperObservationMonitoringRecordV1",
    "PaperObservationMonitoringState",
    "PaperObservationOutcome",
    "PaperObservationSourceKind",
    "PaperObservationTrackProjectionV1",
    "PaperObservationTrackState",
    "PaperObservationTrackV1",
    "create_paper_observation_track",
    "make_event",
    "make_market_fact",
    "make_monitoring_record",
]
