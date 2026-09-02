"""WO-15A versioned downstream timing-handoff trust boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo15 import (
    WO15_CONTRACT_VERSION,
    Wo15ContractError,
    Wo15CycleEvaluation,
    Wo15QualificationPath,
    Wo15TimingState,
    Wo15Wo13Handoff,
)


WO15_TIMING_HANDOFF_IDENTITY = "KRONOS-INTRADAY-WO15-TIMING-HANDOFF-V1"
WO15_TIMING_HANDOFF_VERSION = "1.0.0"
WO15_RISK_REFERENCE_SEMANTICS = "AUDIT_CONTEXT_ONLY"


@dataclass(frozen=True, slots=True)
class Wo15TimingHandoff:
    handoff_identity: str
    handoff_integrity: str
    wo13_trade_plan_identity: str
    wo13_trade_plan_integrity: str
    timing_cycle_id: str
    timing_cycle_integrity: str
    timing_observation_identity: str
    timing_observation_integrity: str
    timing_transition_identity: str
    timing_transition_integrity: str
    prior_state: Wo15TimingState
    current_state: Wo15TimingState
    transition_cause: str
    direction: SemanticDirection
    setup_family: Wo13SetupFamily
    entry_reference: Decimal
    qualification_path: Wo15QualificationPath
    completed_five_minute_evidence_identity: str
    completed_five_minute_evidence_integrity: str
    evidence_boundary: datetime
    cycle_created_at: datetime
    observation_timestamp: datetime
    handoff_created_at: datetime
    research_references: tuple[str, ...]
    session_identity: str
    calendar_identity: str
    calendar_version: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    policy_identity: str
    policy_version: str
    policy_checksum: str
    wo14_observation_identity: str | None
    wo14_observation_integrity: str | None
    wo14_reference_semantics: str | None
    predecessor_handoff_identity: str | None
    supersession_lineage_identity: str | None
    provenance: tuple[str, ...]
    schema_identity: str = WO15_TIMING_HANDOFF_IDENTITY
    schema_version: str = WO15_TIMING_HANDOFF_VERSION
    timing_evidence_authority: bool = True
    sponsor_decision_authority: str = "NONE"
    paper_authority: str = "NONE"
    live_authority: str = "NONE"
    ignore_authority: str = "NONE"
    position_authority: str = "NONE"
    broker_authority: str = "NONE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_reference", _decimal(self.entry_reference))
        values = _without(self, "handoff_identity", "handoff_integrity")
        supported = {
            Wo15TimingState.TIMING_QUALIFIED,
            Wo15TimingState.TIMING_FAILED,
            Wo15TimingState.TIMING_EXPIRED,
            Wo15TimingState.TIMING_UNAVAILABLE,
        }
        risk_values = (
            self.wo14_observation_identity,
            self.wo14_observation_integrity,
            self.wo14_reference_semantics,
        )
        if (
            not _texts((
                self.wo13_trade_plan_identity,
                self.wo13_trade_plan_integrity,
                self.timing_cycle_id,
                self.timing_cycle_integrity,
                self.timing_observation_identity,
                self.timing_observation_integrity,
                self.timing_transition_identity,
                self.timing_transition_integrity,
                self.transition_cause,
                self.completed_five_minute_evidence_identity,
                self.completed_five_minute_evidence_integrity,
                self.session_identity,
                self.calendar_identity,
                self.calendar_version,
                self.instrument_identity,
                self.policy_identity,
                self.policy_version,
                self.policy_checksum,
                *self.provenance,
            ))
            or type(self.prior_state) is not Wo15TimingState
            or self.current_state not in supported
            or type(self.direction) is not SemanticDirection
            or type(self.setup_family) is not Wo13SetupFamily
            or type(self.qualification_path) is not Wo15QualificationPath
            or not self.entry_reference.is_finite()
            or not all(_aware(item) for item in (
                self.evidence_boundary, self.cycle_created_at,
                self.observation_timestamp, self.handoff_created_at,
            ))
            or self.evidence_boundary > self.observation_timestamp
            or self.cycle_created_at > self.observation_timestamp
            or self.observation_timestamp > self.handoff_created_at
            or not _optional_texts(self.research_references)
            or not (
                all(item is None for item in risk_values)
                or all(_text(item) for item in risk_values)
            )
            or self.wo14_reference_semantics is not None
            and self.wo14_reference_semantics != WO15_RISK_REFERENCE_SEMANTICS
            or self.predecessor_handoff_identity is not None
            and not _text(self.predecessor_handoff_identity)
            or self.supersession_lineage_identity is not None
            and not _text(self.supersession_lineage_identity)
            or self.schema_identity != WO15_TIMING_HANDOFF_IDENTITY
            or self.schema_version != WO15_TIMING_HANDOFF_VERSION
            or self.timing_evidence_authority is not True
            or any(item != "NONE" for item in (
                self.sponsor_decision_authority, self.paper_authority,
                self.live_authority, self.ignore_authority,
                self.position_authority, self.broker_authority,
            ))
            or self.handoff_identity != _identity("INTRADAY-WO15-TIMING-HANDOFF-", values)
            or self.handoff_integrity
            != _identity("INTEGRITY-INTRADAY-WO15-TIMING-HANDOFF-", values)
        ):
            raise Wo15ContractError("WO15_TIMING_HANDOFF_INVALID")


def create_wo15_timing_handoff(
    *,
    admission: Wo15Wo13Handoff,
    evaluation: Wo15CycleEvaluation,
    handoff_created_at: datetime,
    research_references: tuple[str, ...] = (),
    wo14_observation_identity: str | None = None,
    wo14_observation_integrity: str | None = None,
    predecessor: Wo15TimingHandoff | None = None,
    supersession_lineage_identity: str | None = None,
    provenance: tuple[str, ...] = ("ADR-0025", "WO-15A"),
) -> Wo15TimingHandoff:
    """Create a terminal/qualified evidence handoff; repeated WAITING is omitted."""

    if type(admission) is not Wo15Wo13Handoff or type(evaluation) is not Wo15CycleEvaluation:
        raise Wo15ContractError("WO15_TIMING_HANDOFF_INPUT_INVALID")
    admission.__post_init__()
    evaluation.__post_init__()
    cycle = evaluation.cycle
    observation = evaluation.observation
    transition = evaluation.transition
    if (
        cycle.wo13_trade_plan_identity != admission.wo13_trade_plan_identity
        or cycle.wo13_trade_plan_integrity != admission.wo13_trade_plan_integrity
        or cycle.canonical_subject_identity != admission.canonical_subject_identity
        or cycle.direction is not admission.direction
        or cycle.setup_family is not admission.setup_family
        or cycle.entry_reference != admission.entry_reference
        or cycle.instrument_identity != admission.instrument_identity
        or cycle.actual_contract_identity != admission.actual_contract_identity
        or cycle.roll_lineage_identity != admission.roll_lineage_identity
    ):
        raise Wo15ContractError("WO15_TIMING_HANDOFF_BINDING_INVALID")
    if transition.current_state is Wo15TimingState.TIMING_WAITING:
        raise Wo15ContractError("WO15_WAITING_HANDOFF_NOT_REQUIRED")
    risk_supplied = wo14_observation_identity is not None or wo14_observation_integrity is not None
    if risk_supplied and not _texts((wo14_observation_identity, wo14_observation_integrity)):
        raise Wo15ContractError("WO15_WO14_REFERENCE_INVALID")
    if predecessor is not None:
        predecessor.__post_init__()
        if (
            predecessor.wo13_trade_plan_identity != admission.wo13_trade_plan_identity
            or predecessor.timing_cycle_id != cycle.timing_cycle_id
            or predecessor.current_state is not Wo15TimingState.TIMING_QUALIFIED
            or transition.current_state not in {
                Wo15TimingState.TIMING_FAILED,
                Wo15TimingState.TIMING_EXPIRED,
            }
        ):
            raise Wo15ContractError("WO15_PREDECESSOR_HANDOFF_INVALID")
    values = {
        "wo13_trade_plan_identity": admission.wo13_trade_plan_identity,
        "wo13_trade_plan_integrity": admission.wo13_trade_plan_integrity,
        "timing_cycle_id": cycle.timing_cycle_id,
        "timing_cycle_integrity": cycle.timing_cycle_integrity,
        "timing_observation_identity": observation.observation_identity,
        "timing_observation_integrity": observation.observation_integrity,
        "timing_transition_identity": transition.transition_identity,
        "timing_transition_integrity": transition.transition_integrity,
        "prior_state": transition.prior_state,
        "current_state": transition.current_state,
        "transition_cause": transition.cause,
        "direction": admission.direction,
        "setup_family": admission.setup_family,
        "entry_reference": admission.entry_reference,
        "qualification_path": observation.qualification_path,
        "completed_five_minute_evidence_identity": (
            observation.completed_five_minute_evidence_identity
        ),
        "completed_five_minute_evidence_integrity": (
            observation.completed_five_minute_evidence_integrity
        ),
        "evidence_boundary": observation.observation_boundary,
        "cycle_created_at": cycle.cycle_created_at,
        "observation_timestamp": observation.observed_at,
        "handoff_created_at": handoff_created_at,
        "research_references": research_references,
        "session_identity": cycle.session_identity,
        "calendar_identity": cycle.calendar_identity,
        "calendar_version": cycle.calendar_version,
        "instrument_identity": cycle.instrument_identity,
        "actual_contract_identity": cycle.actual_contract_identity,
        "roll_lineage_identity": cycle.roll_lineage_identity,
        "policy_identity": cycle.policy.policy_identity,
        "policy_version": cycle.policy.policy_version,
        "policy_checksum": cycle.policy.policy_checksum,
        "wo14_observation_identity": wo14_observation_identity,
        "wo14_observation_integrity": wo14_observation_integrity,
        "wo14_reference_semantics": (
            WO15_RISK_REFERENCE_SEMANTICS if risk_supplied else None
        ),
        "predecessor_handoff_identity": (
            None if predecessor is None else predecessor.handoff_identity
        ),
        "supersession_lineage_identity": supersession_lineage_identity,
        "provenance": provenance,
        "schema_identity": WO15_TIMING_HANDOFF_IDENTITY,
        "schema_version": WO15_TIMING_HANDOFF_VERSION,
        "timing_evidence_authority": True,
        "sponsor_decision_authority": "NONE",
        "paper_authority": "NONE",
        "live_authority": "NONE",
        "ignore_authority": "NONE",
        "position_authority": "NONE",
        "broker_authority": "NONE",
    }
    return Wo15TimingHandoff(
        handoff_identity=_identity("INTRADAY-WO15-TIMING-HANDOFF-", values),
        handoff_integrity=_identity(
            "INTEGRITY-INTRADAY-WO15-TIMING-HANDOFF-", values
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
        raise Wo15ContractError("WO15_DECIMAL_INVALID") from error
    if not result.is_finite():
        raise Wo15ContractError("WO15_DECIMAL_INVALID")
    return result


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(item) for item in values)


def _optional_texts(values: Sequence[object]) -> bool:
    return all(_text(item) for item in values)
