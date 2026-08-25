"""Observation-phase Sponsor choice evidence, separate from position activation.

Governed by ADR-0015 / SPONSOR-OBS-01.  These records preserve what the
Sponsor saw and chose.  They carry no Risk, execution, position, monitoring,
or broker authority.
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

from kronos.swing.v1.analytical_promotion import Kr370AnalyticalPromotionRecord
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.step31_observation import (
    Step31ObservationEvidence,
    Step31SponsorObservationHandoff,
    Step31WarningSeverity,
)


SPONSOR_OBSERVATION_DECISION_CONTRACT_ID = (
    "KRONOS-SWING-SPONSOR-OBSERVATION-DECISION-V1"
)
SPONSOR_DECISION_SNAPSHOT_CONTRACT_ID = (
    "KRONOS-SWING-SPONSOR-DECISION-SNAPSHOT-V1"
)
SPONSOR_ACTIVATION_DISPOSITION_CONTRACT_ID = (
    "KRONOS-SWING-SPONSOR-ACTIVATION-DISPOSITION-V1"
)
SPONSOR_OBSERVATION_POLICY_ID = "SWING-SPONSOR-OBSERVATION-DECISION-V1"
SPONSOR_OBSERVATION_POLICY_VERSION = "1"
SPONSOR_OBSERVATION_STORE_SCHEMA = "KRONOS-SWING-SPONSOR-OBSERVATION-STORE-V1"
SPONSOR_OBSERVATION_AUTHORITY = (
    "SPONSOR_JUDGMENT_EVIDENCE_ONLY_NO_RISK_POSITION_EXECUTION_OR_BROKER_AUTHORITY"
)


class SponsorObservationReason(StrEnum):
    AGREE_WITH_KRONOS = "AGREE_WITH_KRONOS"
    POOR_RR = "POOR_RR"
    STEP31_WARNING = "STEP31_WARNING"
    MARKET_CONTEXT = "MARKET_CONTEXT"
    PERSONAL_RISK_LIMIT = "PERSONAL_RISK_LIMIT"
    TESTING_SETUP = "TESTING_SETUP"
    OTHER = "OTHER"


class SponsorActivationDisposition(StrEnum):
    PENDING_ENTRY_CONFIRMATION = "PENDING_ENTRY_CONFIRMATION"
    ACTIVATED = "ACTIVATED"
    BLOCKED_RISK_REJECTED = "BLOCKED_RISK_REJECTED"
    BLOCKED_RISK_UNAVAILABLE = "BLOCKED_RISK_UNAVAILABLE"
    BLOCKED_CONSTRAINT = "BLOCKED_CONSTRAINT"
    BLOCKED_MISSING_VALID_PLAN = "BLOCKED_MISSING_VALID_PLAN"
    NOT_APPLICABLE_IGNORE = "NOT_APPLICABLE_IGNORE"


@dataclass(frozen=True, slots=True)
class SponsorDecisionSnapshotV1:
    snapshot_identity: str
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    direction: V1Direction
    kr370_identity: str
    kr370_integrity_sha256: str
    kr370_state: str
    kr370_criteria: tuple[tuple[str, str], ...]
    kr370_hard_gate_state: str
    visual_evidence_identity: str
    visual_evidence_sha256: str
    step31_observation_identity: str
    step31_observation_sha256: str
    step31_geometry_status: str
    step31_severity: Step31WarningSeverity
    step31_warnings: tuple[str, ...]
    entry: Decimal | None
    stop: Decimal | None
    target: Decimal | None
    invalidation: Decimal | None
    risk_distance: Decimal | None
    reward_distance: Decimal | None
    risk_reward_ratio: Decimal | None
    risk_reward_state: str
    conventional_trade_plan_identity: str | None
    conventional_trade_plan_sha256: str | None
    risk_identity: str | None
    risk_state: str
    execution_context_identity: str
    mcx_supporting_context_identity: str | None
    mcx_supporting_context_sha256: str | None
    snapshot_timestamp: datetime
    integrity_sha256: str
    contract_identity: str = SPONSOR_DECISION_SNAPSHOT_CONTRACT_ID
    contract_version: str = "1"
    policy_identity: str = SPONSOR_OBSERVATION_POLICY_ID
    policy_version: str = SPONSOR_OBSERVATION_POLICY_VERSION
    authority: str = SPONSOR_OBSERVATION_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not _identity(self.snapshot_identity)
            or not self.native_run_identity
            or not self.canonical_instrument
            or not _digest(self.native_assessment_sha256)
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not _identity(self.kr370_identity)
            or not _digest(self.kr370_integrity_sha256)
            or self.kr370_state not in {"BUY_NOW", "SELL_NOW"}
            or tuple(item[0] for item in self.kr370_criteria)
            != (
                "K1_1H_DIRECTIONAL_PROGRESSION",
                "K2_1H_CPR_ACCEPTANCE",
                "K3_IMMEDIATE_PATH_CLEARANCE",
                "K4_SETUP_QUALITY",
                "K5_NON_EXTENSION",
            )
            or not self.kr370_hard_gate_state
            or not _identity(self.visual_evidence_identity)
            or not _digest(self.visual_evidence_sha256)
            or not _identity(self.step31_observation_identity)
            or not _digest(self.step31_observation_sha256)
            or not self.step31_geometry_status
            or type(self.step31_severity) is not Step31WarningSeverity
            or type(self.step31_warnings) is not tuple
            or any(not _code(item) for item in self.step31_warnings)
            or any(value is not None and not _finite_decimal(value) for value in (
                self.entry, self.stop, self.target, self.invalidation,
                self.risk_distance, self.reward_distance, self.risk_reward_ratio,
            ))
            or (self.conventional_trade_plan_identity is None)
            != (self.conventional_trade_plan_sha256 is None)
            or (
                self.conventional_trade_plan_identity is not None
                and (
                    not _identity(self.conventional_trade_plan_identity)
                    or not _digest(self.conventional_trade_plan_sha256)
                )
            )
            or self.risk_state not in {
                "RISK_APPROVED", "RISK_CONSTRAINED", "RISK_REJECTED", "RISK_UNAVAILABLE"
            }
            or (self.risk_identity is not None and not _identity(self.risk_identity))
            or not _identity(self.execution_context_identity)
            or (self.mcx_supporting_context_identity is None)
            != (self.mcx_supporting_context_sha256 is None)
            or (
                self.mcx_supporting_context_identity is not None
                and (
                    not _identity(self.mcx_supporting_context_identity)
                    or not _digest(self.mcx_supporting_context_sha256)
                )
            )
            or not _aware(self.snapshot_timestamp)
            or self.contract_identity != SPONSOR_DECISION_SNAPSHOT_CONTRACT_ID
            or self.contract_version != "1"
            or self.policy_identity != SPONSOR_OBSERVATION_POLICY_ID
            or self.policy_version != SPONSOR_OBSERVATION_POLICY_VERSION
            or self.authority != SPONSOR_OBSERVATION_AUTHORITY
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("SPONSOR_DECISION_SNAPSHOT_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorObservationDecisionV1:
    decision_identity: str
    snapshot_identity: str
    snapshot_sha256: str
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    direction: V1Direction
    kr370_state: str
    choice: SponsorTradeChoice
    sponsor_reason: SponsorObservationReason | None
    warning_acknowledged: bool
    decision_timestamp: datetime
    integrity_sha256: str
    contract_identity: str = SPONSOR_OBSERVATION_DECISION_CONTRACT_ID
    contract_version: str = "1"
    policy_identity: str = SPONSOR_OBSERVATION_POLICY_ID
    policy_version: str = SPONSOR_OBSERVATION_POLICY_VERSION
    authority: str = SPONSOR_OBSERVATION_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not _identity(self.decision_identity)
            or not _identity(self.snapshot_identity)
            or not _digest(self.snapshot_sha256)
            or not self.native_run_identity
            or not self.canonical_instrument
            or not _digest(self.native_assessment_sha256)
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or self.kr370_state not in {"BUY_NOW", "SELL_NOW"}
            or type(self.choice) is not SponsorTradeChoice
            or (self.sponsor_reason is not None and type(self.sponsor_reason) is not SponsorObservationReason)
            or type(self.warning_acknowledged) is not bool
            or not _aware(self.decision_timestamp)
            or self.contract_identity != SPONSOR_OBSERVATION_DECISION_CONTRACT_ID
            or self.contract_version != "1"
            or self.policy_identity != SPONSOR_OBSERVATION_POLICY_ID
            or self.policy_version != SPONSOR_OBSERVATION_POLICY_VERSION
            or self.authority != SPONSOR_OBSERVATION_AUTHORITY
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("SPONSOR_OBSERVATION_DECISION_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorActivationDispositionV1:
    disposition_identity: str
    decision_identity: str
    disposition: SponsorActivationDisposition
    reason: str
    existing_sponsor_decision_identity: str | None
    sponsor_position_identity: str | None
    recorded_at: datetime
    integrity_sha256: str
    contract_identity: str = SPONSOR_ACTIVATION_DISPOSITION_CONTRACT_ID
    contract_version: str = "1"
    authority: str = "FACTUAL_ACTIVATION_OUTCOME_ONLY_NO_ACTIVATION_AUTHORITY"

    def __post_init__(self) -> None:
        active = self.disposition is SponsorActivationDisposition.ACTIVATED
        if (
            not _identity(self.disposition_identity)
            or not _identity(self.decision_identity)
            or type(self.disposition) is not SponsorActivationDisposition
            or not _code(self.reason)
            or active != (self.existing_sponsor_decision_identity is not None)
            or active != (self.sponsor_position_identity is not None)
            or (
                self.existing_sponsor_decision_identity is not None
                and not _identity(self.existing_sponsor_decision_identity)
            )
            or (
                self.sponsor_position_identity is not None
                and not _identity(self.sponsor_position_identity)
            )
            or not _aware(self.recorded_at)
            or self.contract_identity != SPONSOR_ACTIVATION_DISPOSITION_CONTRACT_ID
            or self.contract_version != "1"
            or self.authority != "FACTUAL_ACTIVATION_OUTCOME_ONLY_NO_ACTIVATION_AUTHORITY"
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("SPONSOR_ACTIVATION_DISPOSITION_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorObservationDecisionResult:
    snapshot: SponsorDecisionSnapshotV1
    decision: SponsorObservationDecisionV1
    activation: SponsorActivationDispositionV1


@dataclass(frozen=True, slots=True)
class JournalObservationHandoffV1:
    snapshot_identity: str
    decision_identity: str
    choice: SponsorTradeChoice
    activation_disposition: SponsorActivationDisposition
    step31_observation_identity: str
    conventional_trade_plan_identity: str | None
    risk_identity: str | None
    risk_state: str
    kr370_identity: str
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    sponsor_position_identity: str | None


def record_sponsor_observation_decision(
    promotion: Kr370AnalyticalPromotionRecord,
    observation: Step31ObservationEvidence,
    handoff: Step31SponsorObservationHandoff,
    choice: SponsorTradeChoice,
    disposition: SponsorActivationDisposition,
    *,
    current_run_identity: str,
    decided_at: datetime,
    warning_acknowledged: bool,
    sponsor_reason: SponsorObservationReason | None = None,
    risk_identity: str | None = None,
    risk_state: str = "RISK_UNAVAILABLE",
    existing_sponsor_decision_identity: str | None = None,
    sponsor_position_identity: str | None = None,
    mcx_supporting_context_identity: str | None = None,
    mcx_supporting_context_sha256: str | None = None,
) -> SponsorObservationDecisionResult:
    """Create immutable observation evidence after all currentness gates pass."""

    if (
        type(promotion) is not Kr370AnalyticalPromotionRecord
        or current_run_identity != promotion.run_identity
        or observation.native_run_identity != promotion.run_identity
        or handoff.native_run_identity != promotion.run_identity
        or observation.canonical_instrument != promotion.canonical_instrument
        or handoff.canonical_instrument != promotion.canonical_instrument
        or observation.native_assessment_sha256 != promotion.native_assessment_sha256
        or handoff.native_assessment_sha256 != promotion.native_assessment_sha256
        or handoff.kr370_handoff_identity != observation.kr370_handoff_identity
        or handoff.observation_evidence_id != observation.observation_evidence_id
        or handoff.observation_evidence_sha256 != observation.integrity_sha256
        or promotion.classification.value not in {"BUY_NOW", "SELL_NOW"}
        or promotion.hard_gate_reason is not None
    ):
        raise ValueError("SPONSOR_OBSERVATION_TRUST_BINDING_INVALID")
    if not _aware(decided_at) or type(choice) is not SponsorTradeChoice:
        raise ValueError("SPONSOR_OBSERVATION_REQUEST_INVALID")
    if (
        observation.severity is Step31WarningSeverity.RED
        and choice in {SponsorTradeChoice.PAPER, SponsorTradeChoice.LIVE}
        and warning_acknowledged is not True
    ):
        raise ValueError("SPONSOR_OBSERVATION_WARNING_ACKNOWLEDGEMENT_REQUIRED")
    if choice is SponsorTradeChoice.IGNORE:
        if disposition is not SponsorActivationDisposition.NOT_APPLICABLE_IGNORE:
            raise ValueError("SPONSOR_OBSERVATION_ACTIVATION_DISPOSITION_INVALID")
    elif disposition is SponsorActivationDisposition.NOT_APPLICABLE_IGNORE:
        raise ValueError("SPONSOR_OBSERVATION_ACTIVATION_DISPOSITION_INVALID")
    elif risk_state == "RISK_REJECTED" and disposition is not SponsorActivationDisposition.BLOCKED_RISK_REJECTED:
        raise ValueError("SPONSOR_OBSERVATION_ACTIVATION_DISPOSITION_INVALID")
    elif risk_state == "RISK_UNAVAILABLE" and disposition is not SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE:
        raise ValueError("SPONSOR_OBSERVATION_ACTIVATION_DISPOSITION_INVALID")
    elif risk_state == "RISK_CONSTRAINED" and disposition not in {
        SponsorActivationDisposition.ACTIVATED,
        SponsorActivationDisposition.BLOCKED_CONSTRAINT,
    }:
        raise ValueError("SPONSOR_OBSERVATION_ACTIVATION_DISPOSITION_INVALID")
    elif risk_state == "RISK_APPROVED" and observation.conventional_trade_plan_id is None and disposition is not SponsorActivationDisposition.BLOCKED_MISSING_VALID_PLAN:
        raise ValueError("SPONSOR_OBSERVATION_ACTIVATION_DISPOSITION_INVALID")
    if disposition is SponsorActivationDisposition.ACTIVATED and (
        observation.conventional_trade_plan_id is None
        or risk_state not in {"RISK_APPROVED", "RISK_CONSTRAINED"}
        or existing_sponsor_decision_identity is None
        or sponsor_position_identity is None
    ):
        raise ValueError("SPONSOR_OBSERVATION_ACTIVATION_DISPOSITION_INVALID")

    visual_digest = sha256(_canonical(promotion.visual_evidence_bindings)).hexdigest()
    snapshot_seed = (
        observation.integrity_sha256,
        promotion.integrity_sha256,
        choice.value,
        decided_at.isoformat(),
    )
    snapshot_identity = _id("SPONSOR-DECISION-SNAPSHOT", *snapshot_seed)
    snapshot_values = dict(
        snapshot_identity=snapshot_identity,
        native_run_identity=promotion.run_identity,
        canonical_instrument=promotion.canonical_instrument,
        native_assessment_sha256=promotion.native_assessment_sha256,
        direction=promotion.direction,
        kr370_identity=promotion.contract_identity + ":" + promotion.integrity_sha256,
        kr370_integrity_sha256=promotion.integrity_sha256,
        kr370_state=promotion.classification.value,
        kr370_criteria=tuple((item.identity.value, item.state.value) for item in promotion.criteria),
        kr370_hard_gate_state=promotion.hard_gate_reason or "NO_HARD_GATE",
        visual_evidence_identity=promotion.review_pack_identity,
        visual_evidence_sha256=visual_digest,
        step31_observation_identity=observation.observation_evidence_id,
        step31_observation_sha256=observation.integrity_sha256,
        step31_geometry_status=observation.geometry_status.value,
        step31_severity=observation.severity,
        step31_warnings=tuple(item.value for item in observation.warnings),
        entry=observation.entry,
        stop=observation.stop,
        target=observation.canonical_target,
        invalidation=observation.invalidation_reference,
        risk_distance=observation.risk_per_unit,
        reward_distance=observation.reward_per_unit,
        risk_reward_ratio=observation.risk_reward_ratio,
        risk_reward_state=observation.risk_reward_state.value,
        conventional_trade_plan_identity=observation.conventional_trade_plan_id,
        conventional_trade_plan_sha256=observation.conventional_trade_plan_sha256,
        risk_identity=risk_identity,
        risk_state=risk_state,
        execution_context_identity=observation.execution_context_identity,
        mcx_supporting_context_identity=mcx_supporting_context_identity,
        mcx_supporting_context_sha256=mcx_supporting_context_sha256,
        snapshot_timestamp=decided_at,
        contract_identity=SPONSOR_DECISION_SNAPSHOT_CONTRACT_ID,
        contract_version="1",
        policy_identity=SPONSOR_OBSERVATION_POLICY_ID,
        policy_version=SPONSOR_OBSERVATION_POLICY_VERSION,
        authority=SPONSOR_OBSERVATION_AUTHORITY,
        integrity_sha256="",
    )
    snapshot = SponsorDecisionSnapshotV1(**(
        snapshot_values | {"integrity_sha256": _values_digest(snapshot_values)}
    ))
    decision_identity = _id(
        "SPONSOR-OBSERVATION-DECISION", snapshot_identity, choice.value
    )
    decision_values = dict(
        decision_identity=decision_identity,
        snapshot_identity=snapshot_identity,
        snapshot_sha256=snapshot.integrity_sha256,
        native_run_identity=promotion.run_identity,
        canonical_instrument=promotion.canonical_instrument,
        native_assessment_sha256=promotion.native_assessment_sha256,
        direction=promotion.direction,
        kr370_state=promotion.classification.value,
        choice=choice,
        sponsor_reason=sponsor_reason,
        warning_acknowledged=warning_acknowledged,
        decision_timestamp=decided_at,
        contract_identity=SPONSOR_OBSERVATION_DECISION_CONTRACT_ID,
        contract_version="1",
        policy_identity=SPONSOR_OBSERVATION_POLICY_ID,
        policy_version=SPONSOR_OBSERVATION_POLICY_VERSION,
        authority=SPONSOR_OBSERVATION_AUTHORITY,
        integrity_sha256="",
    )
    decision = SponsorObservationDecisionV1(**(
        decision_values | {"integrity_sha256": _values_digest(decision_values)}
    ))
    disposition_identity = _id(
        "SPONSOR-ACTIVATION-DISPOSITION", decision_identity, disposition.value
    )
    activation_values = dict(
        disposition_identity=disposition_identity,
        decision_identity=decision_identity,
        disposition=disposition,
        reason=disposition.value,
        existing_sponsor_decision_identity=existing_sponsor_decision_identity,
        sponsor_position_identity=sponsor_position_identity,
        recorded_at=decided_at,
        contract_identity=SPONSOR_ACTIVATION_DISPOSITION_CONTRACT_ID,
        contract_version="1",
        authority="FACTUAL_ACTIVATION_OUTCOME_ONLY_NO_ACTIVATION_AUTHORITY",
        integrity_sha256="",
    )
    activation = SponsorActivationDispositionV1(**(
        activation_values | {"integrity_sha256": _values_digest(activation_values)}
    ))
    return SponsorObservationDecisionResult(snapshot, decision, activation)


class LocalSponsorObservationDecisionStore:
    """Append-only, restart-safe observation-decision evidence store."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("SPONSOR_OBSERVATION_STORE_INVALID")
        self._lock = RLock()

    def retain(self, result: SponsorObservationDecisionResult) -> SponsorObservationDecisionResult:
        if type(result) is not SponsorObservationDecisionResult:
            raise TypeError("SPONSOR_OBSERVATION_RESULT_INVALID")
        path = self._path(result.snapshot.native_run_identity, result.snapshot.canonical_instrument)
        payload = {"schema": SPONSOR_OBSERVATION_STORE_SCHEMA, "result": _primitive(result)}
        with self._lock:
            if path.exists():
                restored = self.load(path)
                if restored != result:
                    raise ValueError("SPONSOR_OBSERVATION_DECISION_ALREADY_FINAL")
                return restored
            _atomic(path, payload)
        return result

    def transition_activation(
        self, result: SponsorObservationDecisionResult
    ) -> SponsorObservationDecisionResult:
        """Append one terminal activation outcome without rewriting Sponsor intent."""

        if type(result) is not SponsorObservationDecisionResult:
            raise TypeError("SPONSOR_OBSERVATION_RESULT_INVALID")
        decision_path = self._path(
            result.snapshot.native_run_identity,
            result.snapshot.canonical_instrument,
        )
        activation_path = self._activation_path(
            result.snapshot.native_run_identity,
            result.snapshot.canonical_instrument,
        )
        with self._lock:
            if not decision_path.exists():
                raise ValueError("SPONSOR_OBSERVATION_DECISION_NOT_FOUND")
            current = self.load(decision_path)
            if current == result:
                return current
            if (
                current.snapshot != result.snapshot
                or current.decision != result.decision
                or current.activation.disposition
                is not SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION
                or result.activation.disposition
                is SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION
            ):
                raise ValueError("SPONSOR_ACTIVATION_TRANSITION_INVALID")
            payload = {
                "schema": SPONSOR_OBSERVATION_STORE_SCHEMA,
                "activation": _primitive(result.activation),
            }
            _atomic(activation_path, payload)
        return result

    def load(self, path: Path) -> SponsorObservationDecisionResult:
        restored = self.load_initial(path)
        activation_path = path.with_name("activation.json")
        if not activation_path.exists():
            return restored
        try:
            transition = json.loads(activation_path.read_text(encoding="utf-8"))
            if transition.get("schema") != SPONSOR_OBSERVATION_STORE_SCHEMA:
                raise ValueError
            activation = _activation_from_dict(transition["activation"])
            if (
                restored.activation.disposition
                is not SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION
                or activation.disposition
                is SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION
                or activation.decision_identity != restored.decision.decision_identity
            ):
                raise ValueError
            return SponsorObservationDecisionResult(
                restored.snapshot, restored.decision, activation
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("SPONSOR_OBSERVATION_STORED_RECORD_INVALID") from error

    def load_initial(self, path: Path) -> SponsorObservationDecisionResult:
        """Restore the immutable decision-time result before any activation transition."""

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema") != SPONSOR_OBSERVATION_STORE_SCHEMA:
                raise ValueError
            result = payload["result"]
            return SponsorObservationDecisionResult(
                _snapshot_from_dict(result["snapshot"]),
                _decision_from_dict(result["decision"]),
                _activation_from_dict(result["activation"]),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("SPONSOR_OBSERVATION_STORED_RECORD_INVALID") from error

    def load_all(self) -> tuple[SponsorObservationDecisionResult, ...]:
        return tuple(self.load(path) for path in sorted(self.root.glob("*/*/decision.json")))

    def load_all_initial(self) -> tuple[SponsorObservationDecisionResult, ...]:
        return tuple(
            self.load_initial(path)
            for path in sorted(self.root.glob("*/*/decision.json"))
        )

    def for_current_observations(
        self, observations: tuple[Step31ObservationEvidence, ...]
    ) -> tuple[SponsorObservationDecisionResult, ...]:
        expected = {
            (item.native_run_identity, item.canonical_instrument): item
            for item in observations
        }
        values = []
        for result in self.load_all():
            observation = expected.get((
                result.snapshot.native_run_identity,
                result.snapshot.canonical_instrument,
            ))
            if observation is None:
                continue
            if (
                result.snapshot.step31_observation_identity != observation.observation_evidence_id
                or result.snapshot.step31_observation_sha256 != observation.integrity_sha256
            ):
                raise ValueError("SPONSOR_OBSERVATION_RESTART_BINDING_INVALID")
            values.append(result)
        return tuple(values)

    def by_choice(self, choice: SponsorTradeChoice) -> tuple[SponsorObservationDecisionResult, ...]:
        return tuple(item for item in self.load_all() if item.decision.choice is choice)

    def by_disposition(
        self, disposition: SponsorActivationDisposition
    ) -> tuple[SponsorObservationDecisionResult, ...]:
        return tuple(item for item in self.load_all() if item.activation.disposition is disposition)

    def by_severity(self, severity: Step31WarningSeverity) -> tuple[SponsorObservationDecisionResult, ...]:
        return tuple(item for item in self.load_all() if item.snapshot.step31_severity is severity)

    def _path(self, run_id: str, instrument: str) -> Path:
        return self.root / run_id / instrument / "decision.json"

    def _activation_path(self, run_id: str, instrument: str) -> Path:
        return self.root / run_id / instrument / "activation.json"


def transition_sponsor_observation_activation(
    result: SponsorObservationDecisionResult,
    disposition: SponsorActivationDisposition,
    *,
    existing_sponsor_decision_identity: str | None,
    sponsor_position_identity: str | None,
    recorded_at: datetime,
) -> SponsorObservationDecisionResult:
    """Create the one terminal factual activation outcome for recorded intent."""

    if (
        type(result) is not SponsorObservationDecisionResult
        or result.activation.disposition
        is not SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION
        or disposition is SponsorActivationDisposition.PENDING_ENTRY_CONFIRMATION
        or not _aware(recorded_at)
    ):
        raise ValueError("SPONSOR_ACTIVATION_TRANSITION_INVALID")
    disposition_identity = _id(
        "SPONSOR-ACTIVATION-DISPOSITION",
        result.decision.decision_identity,
        disposition.value,
    )
    values = dict(
        disposition_identity=disposition_identity,
        decision_identity=result.decision.decision_identity,
        disposition=disposition,
        reason=disposition.value,
        existing_sponsor_decision_identity=existing_sponsor_decision_identity,
        sponsor_position_identity=sponsor_position_identity,
        recorded_at=recorded_at,
        contract_identity=SPONSOR_ACTIVATION_DISPOSITION_CONTRACT_ID,
        contract_version="1",
        authority="FACTUAL_ACTIVATION_OUTCOME_ONLY_NO_ACTIVATION_AUTHORITY",
        integrity_sha256="",
    )
    activation = SponsorActivationDispositionV1(**(
        values | {"integrity_sha256": _values_digest(values)}
    ))
    return SponsorObservationDecisionResult(
        result.snapshot, result.decision, activation
    )


def journal_observation_handoff(result: SponsorObservationDecisionResult) -> JournalObservationHandoffV1:
    return JournalObservationHandoffV1(
        result.snapshot.snapshot_identity,
        result.decision.decision_identity,
        result.decision.choice,
        result.activation.disposition,
        result.snapshot.step31_observation_identity,
        result.snapshot.conventional_trade_plan_identity,
        result.snapshot.risk_identity,
        result.snapshot.risk_state,
        result.snapshot.kr370_identity,
        result.snapshot.native_run_identity,
        result.snapshot.canonical_instrument,
        result.snapshot.native_assessment_sha256,
        result.activation.sponsor_position_identity,
    )


def _snapshot_from_dict(value: dict[str, object]) -> SponsorDecisionSnapshotV1:
    data = dict(value)
    for name in ("entry", "stop", "target", "invalidation", "risk_distance", "reward_distance", "risk_reward_ratio"):
        data[name] = None if data[name] is None else Decimal(str(data[name]))
    data["direction"] = V1Direction(data["direction"])
    data["step31_severity"] = Step31WarningSeverity(data["step31_severity"])
    data["kr370_criteria"] = tuple(tuple(item) for item in data["kr370_criteria"])
    data["step31_warnings"] = tuple(data["step31_warnings"])
    data["snapshot_timestamp"] = datetime.fromisoformat(str(data["snapshot_timestamp"]))
    return SponsorDecisionSnapshotV1(**data)


def _decision_from_dict(value: dict[str, object]) -> SponsorObservationDecisionV1:
    data = dict(value)
    data["direction"] = V1Direction(data["direction"])
    data["choice"] = SponsorTradeChoice(data["choice"])
    data["sponsor_reason"] = None if data["sponsor_reason"] is None else SponsorObservationReason(data["sponsor_reason"])
    data["decision_timestamp"] = datetime.fromisoformat(str(data["decision_timestamp"]))
    return SponsorObservationDecisionV1(**data)


def _activation_from_dict(value: dict[str, object]) -> SponsorActivationDispositionV1:
    data = dict(value)
    data["disposition"] = SponsorActivationDisposition(data["disposition"])
    data["recorded_at"] = datetime.fromisoformat(str(data["recorded_at"]))
    return SponsorActivationDispositionV1(**data)


def _atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _record_digest(record: object) -> str:
    payload = _primitive(record)
    payload["integrity_sha256"] = ""
    return sha256(_canonical(payload)).hexdigest()


def _values_digest(values: dict[str, object]) -> str:
    return sha256(_canonical(values)).hexdigest()


def _id(prefix: str, *parts: str) -> str:
    return prefix + "-" + sha256("|".join(parts).encode("utf-8")).hexdigest()


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(_primitive(value), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _identity(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:@|+/-]{1,512}", value) is not None


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _code(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Z0-9_./ -]{1,256}", value) is not None


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _finite_decimal(value: object) -> bool:
    return type(value) is Decimal and value.is_finite()


__all__ = [
    "JournalObservationHandoffV1",
    "LocalSponsorObservationDecisionStore",
    "SPONSOR_ACTIVATION_DISPOSITION_CONTRACT_ID",
    "SPONSOR_DECISION_SNAPSHOT_CONTRACT_ID",
    "SPONSOR_OBSERVATION_DECISION_CONTRACT_ID",
    "SponsorActivationDisposition",
    "SponsorActivationDispositionV1",
    "SponsorDecisionSnapshotV1",
    "SponsorObservationDecisionResult",
    "SponsorObservationDecisionV1",
    "SponsorObservationReason",
    "journal_observation_handoff",
    "record_sponsor_observation_decision",
    "transition_sponsor_observation_activation",
]
