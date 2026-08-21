"""Bounded KR-370 V1 eligibility handoff into the existing Step-31 engine.

The record proves only that an exact current BUY_NOW / SELL_NOW analytical
promotion may be evaluated by Step-31.  It owns no geometry, Risk, Sponsor
decision, entry-timing, position, alert, execution, or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.analytical_promotion import (
    KR370_PROMOTION_CONTRACT_ID,
    KR370_PROMOTION_CONTRACT_VERSION,
    Kr370AnalyticalClassification,
    Kr370AnalyticalPromotionRecord,
    kr370_promotion_integrity_sha256,
)
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_discovery import NativeOpportunityIdentity
from kronos.swing.v1.native_readiness_v3 import NativeLayer2ReadinessRecordV3
from kronos.swing.v1.native_review import NativeReviewRequirement
from kronos.swing.v1.visual_evidence_v3 import (
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_VERSION,
)


KR370_STEP31_HANDOFF_CONTRACT_ID = "KRONOS-SWING-V1-KR370-STEP31-HANDOFF-V1"
KR370_STEP31_HANDOFF_CONTRACT_VERSION = "1"
KR370_STEP31_HANDOFF_SCHEMA = "KRONOS-SWING-V1-KR370-STEP31-HANDOFF-STORE-V1"
KR370_STEP31_HANDOFF_AUTHORITY = "ELIGIBILITY_HANDOFF_ONLY"


class Kr370Step31HandoffRejected(ValueError):
    """An ineligible, stale, or foreign KR-370 lineage was rejected."""


@dataclass(frozen=True, slots=True)
class Kr370Step31EligibilityHandoff:
    handoff_identity: str
    native_run_identity: str
    canonical_instrument: str
    native_opportunity_identity: NativeOpportunityIdentity
    direction: V1Direction
    native_assessment_sha256: str
    native_requirement_sha256: str
    review_pack_identity: str
    visual_question_set_identity: str
    visual_question_set_version: str
    visual_evidence_bindings: tuple[tuple[str, str, str], ...]
    v3_readiness_identity: str
    v3_readiness_sha256: str
    kr370_record_identity: str
    kr370_record_integrity_sha256: str
    kr370_classification: Kr370AnalyticalClassification
    analysis_boundary: datetime
    observation_boundaries: tuple[tuple[str, datetime], ...]
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_sha256: str
    contract_identity: str = KR370_STEP31_HANDOFF_CONTRACT_ID
    contract_version: str = KR370_STEP31_HANDOFF_CONTRACT_VERSION
    authority: str = KR370_STEP31_HANDOFF_AUTHORITY
    freshness: str = "EXACT_CURRENT_SAME_RUN"
    geometry_authority: bool = False
    risk_authority: bool = False
    sponsor_decision_authority: bool = False
    entry_timing_authority: bool = False
    position_authority: bool = False
    alert_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        expected_direction = (
            V1Direction.LONG
            if self.kr370_classification is Kr370AnalyticalClassification.BUY_NOW
            else V1Direction.SHORT
        )
        if (
            not _identity(self.handoff_identity)
            or not is_swing_analysis_run_id(self.native_run_identity)
            or not self.canonical_instrument
            or type(self.native_opportunity_identity) is not NativeOpportunityIdentity
            or self.direction is not expected_direction
            or not _digest(self.native_assessment_sha256)
            or not _digest(self.native_requirement_sha256)
            or not self.review_pack_identity
            or self.visual_question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or self.visual_question_set_version != VISUAL_QUESTION_SET_V3_VERSION
            or len(self.visual_evidence_bindings) != 4
            or any(
                len(item) != 3 or not _digest(item[1]) or not _digest(item[2])
                for item in self.visual_evidence_bindings
            )
            or not _identity(self.v3_readiness_identity)
            or not _digest(self.v3_readiness_sha256)
            or not _identity(self.kr370_record_identity)
            or not _digest(self.kr370_record_integrity_sha256)
            or self.kr370_classification not in {
                Kr370AnalyticalClassification.BUY_NOW,
                Kr370AnalyticalClassification.SELL_NOW,
            }
            or not _aware(self.analysis_boundary)
            or len(self.observation_boundaries) != 4
            or any(not name or not _aware(boundary) for name, boundary in self.observation_boundaries)
            or not _aware(self.created_at)
            or not self.provenance
            or not _digest(self.integrity_sha256)
            or self.integrity_sha256 != kr370_step31_handoff_integrity_sha256(self)
            or self.contract_identity != KR370_STEP31_HANDOFF_CONTRACT_ID
            or self.contract_version != KR370_STEP31_HANDOFF_CONTRACT_VERSION
            or self.authority != KR370_STEP31_HANDOFF_AUTHORITY
            or self.freshness != "EXACT_CURRENT_SAME_RUN"
            or self.geometry_authority
            or self.risk_authority
            or self.sponsor_decision_authority
            or self.entry_timing_authority
            or self.position_authority
            or self.alert_authority
            or self.execution_authority
            or self.broker_authority
        ):
            raise ValueError("KR370_STEP31_HANDOFF_INVALID")


def create_kr370_step31_handoff(
    requirement: NativeReviewRequirement,
    readiness: NativeLayer2ReadinessRecordV3,
    promotion: Kr370AnalyticalPromotionRecord,
    *,
    current_run_identity: str,
    current_analysis_boundary: datetime,
    created_at: datetime,
) -> Kr370Step31EligibilityHandoff:
    """Create one exact-current eligibility record; every mismatch fails closed."""

    if (
        type(requirement) is not NativeReviewRequirement
        or type(readiness) is not NativeLayer2ReadinessRecordV3
        or type(promotion) is not Kr370AnalyticalPromotionRecord
        or not _aware(current_analysis_boundary)
        or not _aware(created_at)
    ):
        raise Kr370Step31HandoffRejected("KR370_STEP31_INPUT_INVALID")
    if promotion.not_evaluable_reason is not None:
        raise Kr370Step31HandoffRejected("KR370_STEP31_NOT_EVALUABLE")
    if promotion.classification not in {
        Kr370AnalyticalClassification.BUY_NOW,
        Kr370AnalyticalClassification.SELL_NOW,
    }:
        raise Kr370Step31HandoffRejected("KR370_STEP31_CLASSIFICATION_NOT_ELIGIBLE")
    if promotion.integrity_sha256 != kr370_promotion_integrity_sha256(promotion):
        raise Kr370Step31HandoffRejected("KR370_STEP31_PROMOTION_INTEGRITY_INVALID")
    if (
        current_run_identity != requirement.native_run_identity
        or current_run_identity != readiness.run_identity
        or current_run_identity != promotion.run_identity
    ):
        raise Kr370Step31HandoffRejected("KR370_STEP31_CURRENT_RUN_MISMATCH")
    if (
        requirement.canonical_instrument != readiness.canonical_instrument
        or requirement.canonical_instrument != promotion.canonical_instrument
    ):
        raise Kr370Step31HandoffRejected("KR370_STEP31_INSTRUMENT_MISMATCH")
    if (
        requirement.thesis.native_assessment_sha256
        != readiness.native_assessment_sha256
        or requirement.thesis.native_assessment_sha256
        != promotion.native_assessment_sha256
        or requirement.requirement_sha256 != promotion.native_requirement_sha256
    ):
        raise Kr370Step31HandoffRejected("KR370_STEP31_ASSESSMENT_MISMATCH")
    if (
        requirement.thesis.direction is not promotion.direction
        or readiness.question_set_identity != VISUAL_QUESTION_SET_V3_ID
        or readiness.question_set_version != VISUAL_QUESTION_SET_V3_VERSION
        or promotion.visual_question_set_identity != VISUAL_QUESTION_SET_V3_ID
        or promotion.visual_question_set_version != VISUAL_QUESTION_SET_V3_VERSION
    ):
        raise Kr370Step31HandoffRejected("KR370_STEP31_V3_1_BINDING_INVALID")
    readiness_visual = {
        timeframe: (evidence, revision)
        for timeframe, revision, evidence in readiness.visual_bindings
    }
    promotion_visual = {
        timeframe: (evidence, revision)
        for timeframe, evidence, revision in promotion.visual_evidence_bindings
    }
    if readiness_visual != promotion_visual:
        raise Kr370Step31HandoffRejected("KR370_STEP31_VISUAL_EVIDENCE_MISMATCH")
    if (
        current_analysis_boundary != readiness.analysis_boundary
        or current_analysis_boundary != promotion.analysis_boundary
    ):
        raise Kr370Step31HandoffRejected("KR370_STEP31_STALE_PROMOTION")
    expected_observations = tuple(
        (item.timeframe.value, item.observation_boundary)
        for item in requirement.thesis.timeframe_facts
    )
    if promotion.observation_boundaries != expected_observations:
        raise Kr370Step31HandoffRejected("KR370_STEP31_OBSERVATION_BOUNDARY_MISMATCH")

    readiness_identity = f"NATIVE-V3-READINESS-{readiness.result_sha256}"
    kr370_identity = (
        f"{KR370_PROMOTION_CONTRACT_ID}:{KR370_PROMOTION_CONTRACT_VERSION}:"
        f"{promotion.integrity_sha256}"
    )
    values = {
        "native_run_identity": current_run_identity,
        "canonical_instrument": requirement.canonical_instrument,
        "native_opportunity_identity": requirement.thesis.opportunity_identity,
        "direction": promotion.direction,
        "native_assessment_sha256": promotion.native_assessment_sha256,
        "native_requirement_sha256": promotion.native_requirement_sha256,
        "review_pack_identity": promotion.review_pack_identity,
        "visual_question_set_identity": promotion.visual_question_set_identity,
        "visual_question_set_version": promotion.visual_question_set_version,
        "visual_evidence_bindings": promotion.visual_evidence_bindings,
        "v3_readiness_identity": readiness_identity,
        "v3_readiness_sha256": readiness.result_sha256,
        "kr370_record_identity": kr370_identity,
        "kr370_record_integrity_sha256": promotion.integrity_sha256,
        "kr370_classification": promotion.classification,
        "analysis_boundary": promotion.analysis_boundary,
        "observation_boundaries": promotion.observation_boundaries,
        "created_at": created_at,
        "provenance": tuple(dict.fromkeys((
            promotion.review_pack_identity,
            readiness_identity,
            kr370_identity,
            *promotion.provenance,
        ))),
    }
    seed = {key: _primitive(value) for key, value in values.items()}
    handoff_identity = "KR370-STEP31-HANDOFF-" + sha256(_canonical(seed)).hexdigest()
    material = {**values, "handoff_identity": handoff_identity}
    return Kr370Step31EligibilityHandoff(
        **material,
        integrity_sha256=kr370_step31_handoff_integrity_sha256(material),
    )


class LocalKr370Step31HandoffStore:
    """Append-only, exact-binding persistence for the eligibility record."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("KR370_STEP31_HANDOFF_STORE_INVALID")
        self._lock = RLock()

    def retain(self, record: Kr370Step31EligibilityHandoff) -> Path:
        if type(record) is not Kr370Step31EligibilityHandoff:
            raise TypeError("KR370_STEP31_HANDOFF_INVALID")
        path = self.root / record.native_run_identity / record.canonical_instrument / f"{record.integrity_sha256}.json"
        payload = {"schema": KR370_STEP31_HANDOFF_SCHEMA, "record": _primitive(record)}
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("KR370_STEP31_HANDOFF_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load_exact(
        self,
        run_identity: str,
        canonical_instrument: str,
        native_assessment_sha256: str,
        kr370_integrity_sha256: str,
    ) -> Kr370Step31EligibilityHandoff | None:
        root = self.root / run_identity / canonical_instrument
        if not root.exists():
            return None
        matches = []
        for path in sorted(root.glob("*.json")):
            payload = _read(path)
            if payload.get("schema") != KR370_STEP31_HANDOFF_SCHEMA:
                raise ValueError("KR370_STEP31_HANDOFF_RESTORE_SCHEMA_INVALID")
            record = _record_from_dict(payload.get("record"))
            if (
                record.native_assessment_sha256 == native_assessment_sha256
                and record.kr370_record_integrity_sha256 == kr370_integrity_sha256
            ):
                matches.append(record)
        if len(matches) > 1:
            raise ValueError("KR370_STEP31_HANDOFF_RESTORE_AMBIGUOUS")
        return None if not matches else matches[0]


def kr370_step31_handoff_integrity_sha256(
    value: Kr370Step31EligibilityHandoff | dict[str, object],
) -> str:
    material = asdict(value) if type(value) is Kr370Step31EligibilityHandoff else dict(value)
    material.pop("integrity_sha256", None)
    material.setdefault("contract_identity", KR370_STEP31_HANDOFF_CONTRACT_ID)
    material.setdefault("contract_version", KR370_STEP31_HANDOFF_CONTRACT_VERSION)
    material.setdefault("authority", KR370_STEP31_HANDOFF_AUTHORITY)
    material.setdefault("freshness", "EXACT_CURRENT_SAME_RUN")
    for field in (
        "geometry_authority", "risk_authority", "sponsor_decision_authority",
        "entry_timing_authority", "position_authority", "alert_authority",
        "execution_authority", "broker_authority",
    ):
        material.setdefault(field, False)
    return sha256(_canonical(_primitive(material))).hexdigest()


def _record_from_dict(value: object) -> Kr370Step31EligibilityHandoff:
    if type(value) is not dict:
        raise ValueError("KR370_STEP31_HANDOFF_STORED_RECORD_INVALID")
    try:
        data = dict(value)
        data["native_opportunity_identity"] = NativeOpportunityIdentity(data["native_opportunity_identity"])
        data["direction"] = V1Direction(data["direction"])
        data["kr370_classification"] = Kr370AnalyticalClassification(data["kr370_classification"])
        data["visual_evidence_bindings"] = tuple(tuple(item) for item in data["visual_evidence_bindings"])
        data["observation_boundaries"] = tuple(
            (name, datetime.fromisoformat(boundary))
            for name, boundary in data["observation_boundaries"]
        )
        data["analysis_boundary"] = datetime.fromisoformat(data["analysis_boundary"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["provenance"] = tuple(data["provenance"])
        return Kr370Step31EligibilityHandoff(**data)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("KR370_STEP31_HANDOFF_STORED_RECORD_INVALID") from error


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("KR370_STEP31_HANDOFF_STORED_RECORD_INVALID") from error
    if type(value) is not dict:
        raise ValueError("KR370_STEP31_HANDOFF_STORED_RECORD_INVALID")
    return value


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _primitive(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _identity(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:@|+/-]{1,512}", value) is not None


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "KR370_STEP31_HANDOFF_AUTHORITY",
    "KR370_STEP31_HANDOFF_CONTRACT_ID",
    "KR370_STEP31_HANDOFF_CONTRACT_VERSION",
    "Kr370Step31EligibilityHandoff",
    "Kr370Step31HandoffRejected",
    "LocalKr370Step31HandoffStore",
    "create_kr370_step31_handoff",
    "kr370_step31_handoff_integrity_sha256",
]
