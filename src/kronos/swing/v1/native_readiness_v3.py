"""V3 readiness binding for independent visual and deterministic machine facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock

from kronos.swing.v1.mtf_facts import SameRunMtfFactSnapshot
from kronos.swing.v1.native_readiness import (
    EvidenceCompleteness,
    ExtensionCondition,
    NativeConditionInputs,
    NativeLayer2Conditions,
    NativeReadinessState,
    ObstacleCondition,
    ReferenceCondition,
    ThesisIntact,
    build_native_layer2_conditions,
    native_layer2_conditions_from_dict,
    resolve_native_readiness,
)
from kronos.swing.v1.native_review import (
    McxReferenceResult,
    NativeIndependentLayer2Evidence,
    NativeLayer2EvidenceState,
    NativeReviewRequirement,
)
from kronos.swing.v1.reference_facts import (
    CPR_CALCULATION_POLICY_IDENTITY,
    CPR_CALCULATION_POLICY_VERSION,
    REFERENCE_POLICY_IDENTITY,
    REFERENCE_POLICY_VERSION,
    SwingReferenceAvailability,
    SwingReferenceChartTimeframe,
    machine_fact_integrity_sha256,
)
from kronos.swing.v1.visual_evidence_v2 import VisualObservationStatus
from kronos.swing.v1.visual_evidence_v3 import (
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_LEGACY_VERSION,
    VISUAL_QUESTION_SET_V3_VERSION,
    VisualEvidenceV3Response,
    VisualQuestionV3,
    VisualTimeframe,
    VisualV3QualitativeObservation,
)


NATIVE_READINESS_V3_BINDING_POLICY_ID = "SWING-NATIVE-READINESS-V3-EVIDENCE-BINDING"
NATIVE_READINESS_V3_BINDING_POLICY_VERSION = "1.0"
NATIVE_READINESS_V3_RECORD_SCHEMA = "KRONOS-SWING-NATIVE-READINESS-V3"


@dataclass(frozen=True, slots=True)
class NativeV3EvidenceGate:
    invalid: bool
    incomplete: bool
    machine_fact_bindings: tuple[tuple[str, str, str], ...]
    visual_bindings: tuple[tuple[str, str, str], ...]

    def __post_init__(self) -> None:
        if (
            type(self.invalid) is not bool
            or type(self.incomplete) is not bool
            or type(self.machine_fact_bindings) is not tuple
            or type(self.visual_bindings) is not tuple
            or any(len(item) != 3 or not _digest(item[2]) for item in self.machine_fact_bindings)
            or any(len(item) != 3 or not _digest(item[2]) for item in self.visual_bindings)
        ):
            raise ValueError("NATIVE_V3_EVIDENCE_GATE_INVALID")


@dataclass(frozen=True, slots=True)
class NativeLayer2ReadinessRecordV3:
    run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    machine_fact_bindings: tuple[tuple[str, str, str], ...]
    visual_bindings: tuple[tuple[str, str, str], ...]
    visual_evidence_hashes: tuple[str, ...]
    conditions: NativeLayer2Conditions
    readiness: NativeReadinessState
    primary_reason: str
    analysis_boundary: datetime
    created_at: datetime
    result_sha256: str
    question_set_identity: str = VISUAL_QUESTION_SET_V3_ID
    question_set_version: str = VISUAL_QUESTION_SET_V3_VERSION
    binding_policy_identity: str = NATIVE_READINESS_V3_BINDING_POLICY_ID
    binding_policy_version: str = NATIVE_READINESS_V3_BINDING_POLICY_VERSION
    schema: str = NATIVE_READINESS_V3_RECORD_SCHEMA
    authority: str = "READINESS_ONLY_NO_TRADING_OR_EXECUTION_AUTHORITY"

    def __post_init__(self) -> None:
        if (
            not self.run_identity
            or not self.canonical_instrument
            or not _digest(self.native_assessment_sha256)
            or len(self.machine_fact_bindings) != 4
            or len(self.visual_bindings) != 4
            or any(len(item) != 3 or not _digest(item[2]) for item in self.machine_fact_bindings)
            or any(len(item) != 3 or not _digest(item[2]) for item in self.visual_bindings)
            or len(self.visual_evidence_hashes) != 4
            or any(not _digest(item) for item in self.visual_evidence_hashes)
            or type(self.conditions) is not NativeLayer2Conditions
            or type(self.readiness) is not NativeReadinessState
            or not self.primary_reason
            or not _aware(self.analysis_boundary)
            or not _aware(self.created_at)
            or not _digest(self.result_sha256)
            or self.result_sha256 != _record_digest(self)
            or self.question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or self.question_set_version not in {
                VISUAL_QUESTION_SET_V3_LEGACY_VERSION,
                VISUAL_QUESTION_SET_V3_VERSION,
            }
            or self.binding_policy_identity != NATIVE_READINESS_V3_BINDING_POLICY_ID
            or self.binding_policy_version != NATIVE_READINESS_V3_BINDING_POLICY_VERSION
            or self.schema != NATIVE_READINESS_V3_RECORD_SCHEMA
            or self.authority != "READINESS_ONLY_NO_TRADING_OR_EXECUTION_AUTHORITY"
        ):
            raise ValueError("NATIVE_LAYER2_READINESS_V3_RECORD_INVALID")


def evaluate_v3_evidence_gate(
    requirement: NativeReviewRequirement,
    mtf_snapshot: SameRunMtfFactSnapshot,
    visual: tuple[VisualEvidenceV3Response, ...],
) -> NativeV3EvidenceGate:
    """Require independent machine and visual authority for all four timeframes."""

    if (
        type(requirement) is not NativeReviewRequirement
        or type(mtf_snapshot) is not SameRunMtfFactSnapshot
        or mtf_snapshot.run_identity != requirement.native_run_identity
        or type(visual) is not tuple
    ):
        raise ValueError("NATIVE_V3_EVIDENCE_BINDING_INVALID")
    instrument = mtf_snapshot.instrument(requirement.canonical_instrument)
    machine = instrument.reference_facts
    if len(machine) != 4:
        return NativeV3EvidenceGate(False, True, (), ())
    analysis_boundaries = {item.analysis_boundary for item in machine}
    if len(analysis_boundaries) != 1:
        raise ValueError("NATIVE_V3_MACHINE_BOUNDARY_MISMATCH")
    machine_bindings = tuple(
        (
            item.chart_timeframe.value,
            item.reference_period_identity,
            item.integrity_sha256,
        )
        for item in machine
    )
    invalid = any(
        item.run_identity != requirement.native_run_identity
        or item.canonical_instrument != requirement.canonical_instrument
        or item.integrity_sha256 != machine_fact_integrity_sha256(item)
        or item.reference_policy_identity != REFERENCE_POLICY_IDENTITY
        or item.reference_policy_version != REFERENCE_POLICY_VERSION
        or item.calculation_policy_identity != CPR_CALCULATION_POLICY_IDENTITY
        or item.calculation_policy_version != CPR_CALCULATION_POLICY_VERSION
        for item in machine
    )
    incomplete = any(
        item.availability is not SwingReferenceAvailability.AVAILABLE
        for item in machine
    )
    by_timeframe = {item.timeframe: item for item in visual}
    if len(by_timeframe) != len(visual):
        raise ValueError("NATIVE_V3_VISUAL_DUPLICATE_TIMEFRAME")
    visual_bindings = []
    mandatory = set(VisualQuestionV3) - {
        VisualQuestionV3.PINE_VISIBLE_EVIDENCE,
        VisualQuestionV3.VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS,
    }
    for timeframe in VisualTimeframe:
        response = by_timeframe.get(timeframe)
        fact = instrument.reference_fact(
            SwingReferenceChartTimeframe(timeframe.value)
        )
        if response is None:
            incomplete = True
            continue
        if (
            response.native_run_identity != requirement.native_run_identity
            or response.native_assessment_sha256
            != requirement.thesis.native_assessment_sha256
            or response.native_canonical_instrument
            != requirement.canonical_instrument
            or response.analysis_boundary != fact.analysis_boundary
            or response.machine_fact_integrity_sha256 != fact.integrity_sha256
        ):
            raise ValueError("NATIVE_V3_VISUAL_MACHINE_BINDING_INVALID")
        visual_bindings.append(
            (timeframe.value, response.chart_revision_sha256, response.evidence_sha256)
        )
        for observation in response.observations:
            if observation.question_id not in mandatory:
                continue
            if observation.observation_status is VisualObservationStatus.INVALID:
                invalid = True
            elif observation.observation_status is not VisualObservationStatus.OBSERVED:
                incomplete = True
    return NativeV3EvidenceGate(
        invalid, incomplete, machine_bindings, tuple(visual_bindings)
    )


def build_native_layer2_conditions_v3(
    requirement: NativeReviewRequirement,
    layer2: NativeIndependentLayer2Evidence,
    mtf_snapshot: SameRunMtfFactSnapshot,
    visual: tuple[VisualEvidenceV3Response, ...],
    *,
    reference: McxReferenceResult | None = None,
    inputs: NativeConditionInputs = NativeConditionInputs(),
) -> NativeLayer2Conditions:
    """Apply existing readiness categories with the corrected V3 evidence gate."""

    gate = evaluate_v3_evidence_gate(requirement, mtf_snapshot, visual)
    base = build_native_layer2_conditions(
        requirement, layer2, (), reference=reference, inputs=inputs
    )
    invalid = gate.invalid
    incomplete = gate.incomplete or any(
        state is NativeLayer2EvidenceState.UNAVAILABLE
        for _, state in layer2.timeframe_states
    )
    if requirement.mcx_reference is not None:
        if reference is None:
            incomplete = True
        elif base.reference_condition is ReferenceCondition.INVALID:
            invalid = True
        elif base.reference_condition is ReferenceCondition.UNAVAILABLE:
            incomplete = True
    if inputs.retest is None and base.retest_condition.value == "UNAVAILABLE":
        incomplete = True
    completeness = (
        EvidenceCompleteness.INVALID
        if invalid
        else EvidenceCompleteness.INCOMPLETE
        if incomplete
        else EvidenceCompleteness.COMPLETE
    )
    visual_extended = _v3_finding(
        visual,
        VisualQuestionV3.MATURITY_AND_CHASE_CONTEXT,
        "VISIBLY_EXTENDED",
    )
    extension = (
        ExtensionCondition.MATERIAL_EXTENSION
        if base.thesis_intact is ThesisIntact.YES
        and visual_extended
        and inputs.extension is not None
        and inputs.extension.materially_beyond_recent_structure
        else ExtensionCondition.NONE
    )
    visual_obstacle = _v3_observed(
        visual, VisualQuestionV3.VISUAL_OBSTACLE_EVIDENCE
    )
    obstacle = (
        ObstacleCondition.NONE
        if inputs.obstacle is None or not visual_obstacle
        else ObstacleCondition.NONE
        if not inputs.obstacle.adverse_directional_path
        else ObstacleCondition.ADVERSE_BLOCKING
        if inputs.obstacle.clearance_required_for_trade_construction
        else ObstacleCondition.ADVERSE_NON_BLOCKING
    )
    return replace(
        base,
        evidence_completeness=completeness,
        extension_condition=extension,
        obstacle_condition=obstacle,
    )


def create_native_readiness_record_v3(
    requirement: NativeReviewRequirement,
    layer2: NativeIndependentLayer2Evidence,
    mtf_snapshot: SameRunMtfFactSnapshot,
    visual: tuple[VisualEvidenceV3Response, ...],
    *,
    created_at: datetime,
    reference: McxReferenceResult | None = None,
    inputs: NativeConditionInputs = NativeConditionInputs(),
) -> NativeLayer2ReadinessRecordV3:
    versions = {item.question_set_version for item in visual}
    if len(versions) != 1:
        raise ValueError("NATIVE_V3_VISUAL_VERSION_MISMATCH")
    question_set_version = versions.pop()
    gate = evaluate_v3_evidence_gate(requirement, mtf_snapshot, visual)
    conditions = build_native_layer2_conditions_v3(
        requirement,
        layer2,
        mtf_snapshot,
        visual,
        reference=reference,
        inputs=inputs,
    )
    readiness, reason = resolve_native_readiness(conditions)
    machine = mtf_snapshot.instrument(requirement.canonical_instrument).reference_facts
    analysis_boundary = machine[0].analysis_boundary
    ordered = tuple(sorted(visual, key=lambda item: item.timeframe.value))
    values: dict[str, object] = {
        "run_identity": requirement.native_run_identity,
        "canonical_instrument": requirement.canonical_instrument,
        "native_assessment_sha256": requirement.thesis.native_assessment_sha256,
        "machine_fact_bindings": gate.machine_fact_bindings,
        "visual_bindings": gate.visual_bindings,
        "visual_evidence_hashes": tuple(item.evidence_sha256 for item in ordered),
        "conditions": conditions,
        "readiness": readiness,
        "primary_reason": reason,
        "analysis_boundary": analysis_boundary,
        "created_at": created_at,
    }
    return NativeLayer2ReadinessRecordV3(
        **values,  # type: ignore[arg-type]
        result_sha256=_values_digest(values, question_set_version),
        question_set_version=question_set_version,
    )


class NativeLayer2ReadinessV3Store:
    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("NATIVE_READINESS_V3_STORE_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, record: NativeLayer2ReadinessRecordV3) -> Path:
        if type(record) is not NativeLayer2ReadinessRecordV3:
            raise TypeError("NATIVE_READINESS_V3_RECORD_INVALID")
        path = (
            self._root
            / record.run_identity
            / f"{record.canonical_instrument}--{record.result_sha256}.json"
        )
        payload = {"schema": NATIVE_READINESS_V3_RECORD_SCHEMA, "record": _primitive(record)}
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("NATIVE_READINESS_V3_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load_exact(
        self,
        run_identity: str,
        canonical_instrument: str,
        native_assessment_sha256: str,
        visual_evidence_hashes: tuple[str, ...],
    ) -> NativeLayer2ReadinessRecordV3 | None:
        """Restore one exact immutable V3 readiness identity, never a latest value."""

        root = self._root / run_identity
        if not root.exists():
            return None
        matches = []
        for path in sorted(root.glob(f"{canonical_instrument}--*.json")):
            payload = _read(path)
            if payload.get("schema") != NATIVE_READINESS_V3_RECORD_SCHEMA:
                raise ValueError("NATIVE_READINESS_V3_RESTORE_SCHEMA_INVALID")
            record = _record_from_dict(payload.get("record"))
            if (
                record.run_identity == run_identity
                and record.canonical_instrument == canonical_instrument
                and record.native_assessment_sha256 == native_assessment_sha256
                and record.visual_evidence_hashes == visual_evidence_hashes
            ):
                matches.append(record)
        if len(matches) > 1:
            raise ValueError("NATIVE_READINESS_V3_RESTORE_AMBIGUOUS")
        return None if not matches else matches[0]


def _v3_finding(
    values: tuple[VisualEvidenceV3Response, ...],
    question: VisualQuestionV3,
    finding: str,
) -> bool:
    return any(
        isinstance(item, VisualV3QualitativeObservation)
        and item.question_id is question
        and item.observation_status is VisualObservationStatus.OBSERVED
        and item.finding.strip().upper() == finding
        for response in values
        for item in response.observations
    )


def _v3_observed(
    values: tuple[VisualEvidenceV3Response, ...], question: VisualQuestionV3
) -> bool:
    return any(
        item.question_id is question
        and item.observation_status is VisualObservationStatus.OBSERVED
        for response in values
        for item in response.observations
    )


def _values_digest(
    values: dict[str, object], question_set_version: str
) -> str:
    payload = {
        **values,
        "result_sha256": "",
        "question_set_identity": VISUAL_QUESTION_SET_V3_ID,
        "question_set_version": question_set_version,
        "binding_policy_identity": NATIVE_READINESS_V3_BINDING_POLICY_ID,
        "binding_policy_version": NATIVE_READINESS_V3_BINDING_POLICY_VERSION,
        "schema": NATIVE_READINESS_V3_RECORD_SCHEMA,
        "authority": "READINESS_ONLY_NO_TRADING_OR_EXECUTION_AUTHORITY",
    }
    return sha256(_canonical(payload)).hexdigest()


def _record_from_dict(value: object) -> NativeLayer2ReadinessRecordV3:
    if type(value) is not dict:
        raise ValueError("NATIVE_READINESS_V3_RESTORE_INVALID")
    try:
        return NativeLayer2ReadinessRecordV3(
            run_identity=value["run_identity"],
            canonical_instrument=value["canonical_instrument"],
            native_assessment_sha256=value["native_assessment_sha256"],
            machine_fact_bindings=tuple(tuple(item) for item in value["machine_fact_bindings"]),
            visual_bindings=tuple(tuple(item) for item in value["visual_bindings"]),
            visual_evidence_hashes=tuple(value["visual_evidence_hashes"]),
            conditions=native_layer2_conditions_from_dict(value["conditions"]),
            readiness=NativeReadinessState(value["readiness"]),
            primary_reason=value["primary_reason"],
            analysis_boundary=datetime.fromisoformat(value["analysis_boundary"]),
            created_at=datetime.fromisoformat(value["created_at"]),
            result_sha256=value["result_sha256"],
            question_set_identity=value["question_set_identity"],
            question_set_version=value["question_set_version"],
            binding_policy_identity=value["binding_policy_identity"],
            binding_policy_version=value["binding_policy_version"],
            schema=value["schema"],
            authority=value["authority"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("NATIVE_"):
            raise
        raise ValueError("NATIVE_READINESS_V3_RESTORE_INVALID") from error


def _record_digest(record: NativeLayer2ReadinessRecordV3) -> str:
    payload = _primitive(record)
    payload["result_sha256"] = ""
    return sha256(_canonical(payload)).hexdigest()


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("NATIVE_READINESS_V3_INVALID") from error
    if type(value) is not dict:
        raise ValueError("NATIVE_READINESS_V3_INVALID")
    return value


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _primitive(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _primitive(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        _primitive(value), sort_keys=True, separators=(",", ":")
    ).encode()


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "NATIVE_READINESS_V3_BINDING_POLICY_ID",
    "NATIVE_READINESS_V3_BINDING_POLICY_VERSION",
    "NATIVE_READINESS_V3_RECORD_SCHEMA",
    "NativeLayer2ReadinessRecordV3",
    "NativeLayer2ReadinessV3Store",
    "NativeV3EvidenceGate",
    "build_native_layer2_conditions_v3",
    "create_native_readiness_record_v3",
    "evaluate_v3_evidence_gate",
]
