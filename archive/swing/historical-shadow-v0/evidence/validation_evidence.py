"""Numeric review evidence and restart-safe Shadow validation observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json
import os
from pathlib import Path
import re
from threading import RLock
from typing import Callable

from kronos.swing.v1.models import StructuralState, V1Direction, V1Setup
from kronos.swing.v1.shadow_mtf import (
    DailyControlEvidence,
    DailyControlProbableIdentity,
    ShadowCandidateState,
    ShadowInstrumentAssessment,
    ShadowMtfRun,
    ShadowTimeframe,
    TimeframeStructuralEvidence,
)


DEFAULT_SHADOW_VALIDATION_EVIDENCE_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "swing-v1"
    / "shadow-validation"
)


class NumericLevelAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    LEVEL_UNAVAILABLE = "LEVEL_UNAVAILABLE"


class NextConditionAuthority(StrEnum):
    CHART_HEALTH_EVENT = "CHART_HEALTH_EVENT"
    READY_FOR_TRADE_PLAN = "READY_FOR_TRADE_PLAN"


@dataclass(frozen=True, slots=True)
class NumericReferenceEvidence:
    reference_identity: str
    timeframe: str
    observation_boundary: datetime
    source: str
    availability: NumericLevelAvailability
    price: float | None = None
    zone_low: float | None = None
    zone_high: float | None = None

    def __post_init__(self) -> None:
        available = self.availability is NumericLevelAvailability.AVAILABLE
        point = self.price is not None
        zone = self.zone_low is not None or self.zone_high is not None
        if (
            not self.reference_identity
            or self.timeframe not in {"1W", "1D", "4H", "1H"}
            or not _aware(self.observation_boundary)
            or not self.source
            or type(self.availability) is not NumericLevelAvailability
            or (available and point == zone)
            or (not available and (point or zone))
            or (zone and (self.zone_low is None or self.zone_high is None))
            or (zone and self.zone_low > self.zone_high)  # type: ignore[operator]
            or any(
                value is not None and (type(value) is not float or value < 0.0)
                for value in (self.price, self.zone_low, self.zone_high)
            )
        ):
            raise ValueError("NUMERIC_REFERENCE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class AnalyticalClaimEvidence:
    claim: str
    reference: NumericReferenceEvidence
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.claim not in {
                "BARRIER_PRESENT",
                "BREAKOUT",
                "BREAKDOWN",
                "CONSOLIDATION",
                "EXTENDED_FROM_STRUCTURE",
                "WAIT_FOR_ACCEPTANCE",
                "STRUCTURAL_FAILURE",
                "RETEST",
                "SWING_HIGH",
                "SWING_LOW",
                "SMA20",
                "SMA50",
                "SMA200",
                "ANALYTICAL_BOUNDARY_CLOSE",
                "INVALIDATION_RESET",
            }
            or type(self.reference) is not NumericReferenceEvidence
            or not self.provenance
        ):
            raise ValueError("ANALYTICAL_CLAIM_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class NextConditionEvidence:
    condition_type: str
    timeframe: str
    required_event: str
    source: str
    availability: NumericLevelAvailability
    authority: NextConditionAuthority
    reference: NumericReferenceEvidence | None
    ready_for_trade_plan: bool

    def __post_init__(self) -> None:
        if (
            not self.condition_type
            or self.timeframe not in {"1W", "1D", "4H", "1H"}
            or self.required_event
            not in {"CLOSE", "BREAK", "ACCEPTANCE", "RETEST", "PULLBACK"}
            or not self.source
            or type(self.availability) is not NumericLevelAvailability
            or type(self.authority) is not NextConditionAuthority
            or type(self.ready_for_trade_plan) is not bool
            or (
                self.availability is NumericLevelAvailability.AVAILABLE
                and type(self.reference) is not NumericReferenceEvidence
            )
            or (
                self.reference is not None
                and (
                    self.reference.timeframe != self.timeframe
                    or self.reference.availability is not self.availability
                )
            )
            or (
                self.authority is NextConditionAuthority.CHART_HEALTH_EVENT
                and self.ready_for_trade_plan
            )
        ):
            raise ValueError("NEXT_CONDITION_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ReviewNumericEvidenceBundle:
    claims: tuple[AnalyticalClaimEvidence, ...]
    next_condition: NextConditionEvidence | None

    def __post_init__(self) -> None:
        if (
            type(self.claims) is not tuple
            or any(type(item) is not AnalyticalClaimEvidence for item in self.claims)
            or len({item.claim + "|" + item.reference.reference_identity for item in self.claims})
            != len(self.claims)
            or (
                self.next_condition is not None
                and type(self.next_condition) is not NextConditionEvidence
            )
        ):
            raise ValueError("REVIEW_NUMERIC_EVIDENCE_BUNDLE_INVALID")


@dataclass(frozen=True, slots=True)
class SponsorValidationObservation:
    run_identity: str
    canonical_instrument: str
    observed_at: datetime
    observation: str

    def __post_init__(self) -> None:
        if (
            not self.run_identity
            or not re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument)
            or not _aware(self.observed_at)
            or not self.observation.strip()
            or len(self.observation) > 500
            or any(ord(character) < 32 and character not in "\n\t" for character in self.observation)
        ):
            raise ValueError("SPONSOR_VALIDATION_OBSERVATION_INVALID")


class ShadowValidationEvidenceStore:
    """Atomic local evidence store; Sponsor notes never mutate model output."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or not callable(clock):
            raise ValueError("SHADOW_VALIDATION_STORE_INVALID")
        self._root = root
        self._clock = clock
        self._lock = RLock()

    def retain_assessment(
        self,
        assessment: ShadowInstrumentAssessment,
        review_evidence: ReviewNumericEvidenceBundle | None = None,
    ) -> Path:
        if type(assessment) is not ShadowInstrumentAssessment:
            raise ValueError("SHADOW_VALIDATION_ASSESSMENT_INVALID")
        if review_evidence is not None and type(review_evidence) is not ReviewNumericEvidenceBundle:
            raise ValueError("SHADOW_VALIDATION_ASSESSMENT_INVALID")
        path = self._record_path(assessment.run_identity, assessment.canonical_instrument)
        payload = {
            "schema": "KRONOS-SHADOW-MTF-VALIDATION-EVIDENCE-V1",
            "assessment": _json_value(asdict(assessment)),
            "review_numeric_evidence": (
                None if review_evidence is None else _json_value(asdict(review_evidence))
            ),
            "sponsor_observations": [],
        }
        with self._lock:
            if path.exists():
                current = _read_payload(path)
                if (
                    current["assessment"] != payload["assessment"]
                    or current["review_numeric_evidence"]
                    != payload["review_numeric_evidence"]
                ):
                    raise ValueError("SHADOW_VALIDATION_ASSESSMENT_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def retain_run(self, run: ShadowMtfRun) -> Path:
        """Atomically retain one complete immutable same-98 Shadow run."""

        if type(run) is not ShadowMtfRun:
            raise ValueError("SHADOW_VALIDATION_RUN_INVALID")
        path = self._run_path(run.run_identity)
        payload = {
            "schema": "KRONOS-SHADOW-MTF-RUN-EVIDENCE-V1",
            "run": _json_value(asdict(run)),
        }
        with self._lock:
            if path.exists():
                if _read_run_payload(path) != payload:
                    raise ValueError("SHADOW_VALIDATION_RUN_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load_run(self, run_identity: str) -> ShadowMtfRun:
        """Recover a complete retained run without Provider contact."""

        path = self._run_path(run_identity)
        with self._lock:
            payload = _read_run_payload(path)
        return _shadow_run(payload["run"])

    def record_sponsor_observation(
        self,
        assessment: ShadowInstrumentAssessment,
        observation: str,
    ) -> SponsorValidationObservation:
        path = self._record_path(assessment.run_identity, assessment.canonical_instrument)
        if not path.exists():
            self.retain_assessment(assessment)
        item = SponsorValidationObservation(
            assessment.run_identity,
            assessment.canonical_instrument,
            self._clock(),
            observation.strip(),
        )
        path = self._record_path(item.run_identity, item.canonical_instrument)
        with self._lock:
            payload = _read_payload(path)
            payload["sponsor_observations"].append(_json_value(asdict(item)))
            _atomic_json(path, payload)
        return item

    def evidence_payload(self, run_identity: str, canonical_instrument: str) -> dict[str, object]:
        path = self._record_path(run_identity, canonical_instrument)
        with self._lock:
            return _read_payload(path)

    def _record_path(self, run_identity: str, canonical_instrument: str) -> Path:
        safe_run = _safe_component(run_identity)
        safe_instrument = _safe_component(canonical_instrument)
        return self._root / safe_run / f"{safe_instrument}.json"

    def _run_path(self, run_identity: str) -> Path:
        return self._root / "complete-runs" / f"{_safe_component(run_identity)}.json"


def _safe_component(value: str) -> str:
    if not value or not re.fullmatch(r"[A-Za-z0-9&._ -]{1,128}", value):
        raise ValueError("SHADOW_VALIDATION_IDENTITY_INVALID")
    return value.replace(" ", "_").replace("&", "AND")


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _read_payload(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("SHADOW_VALIDATION_EVIDENCE_INVALID") from error
    if (
        type(payload) is not dict
        or set(payload) != {
            "schema",
            "assessment",
            "review_numeric_evidence",
            "sponsor_observations",
        }
        or payload["schema"] != "KRONOS-SHADOW-MTF-VALIDATION-EVIDENCE-V1"
        or type(payload["assessment"]) is not dict
        or type(payload["sponsor_observations"]) is not list
    ):
        raise ValueError("SHADOW_VALIDATION_EVIDENCE_INVALID")
    return payload


def _read_run_payload(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("SHADOW_VALIDATION_RUN_UNAVAILABLE") from error
    if (
        type(payload) is not dict
        or set(payload) != {"schema", "run"}
        or payload["schema"] != "KRONOS-SHADOW-MTF-RUN-EVIDENCE-V1"
        or type(payload["run"]) is not dict
    ):
        raise ValueError("SHADOW_VALIDATION_RUN_INVALID")
    return payload


def _shadow_run(value: object) -> ShadowMtfRun:
    if type(value) is not dict:
        raise ValueError("SHADOW_VALIDATION_RUN_INVALID")
    try:
        assessments = tuple(_shadow_assessment(item) for item in value["assessments"])
        return ShadowMtfRun(
            run_identity=value["run_identity"],
            provider_source_identity=value["provider_source_identity"],
            assessments=assessments,
            control_population_size=value["control_population_size"],
            shadow_population_size=value["shadow_population_size"],
            policy_identity=value["policy_identity"],
            authority=value["authority"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("SHADOW_VALIDATION_RUN_INVALID") from error


def _shadow_assessment(value: object) -> ShadowInstrumentAssessment:
    if type(value) is not dict:
        raise ValueError("SHADOW_VALIDATION_RUN_INVALID")
    control_value = value["control"]
    control = DailyControlEvidence(
        control_value["candidate"],
        None if control_value["setup"] is None else V1Setup(control_value["setup"]),
        V1Direction(control_value["direction"]),
        control_value["reason"],
        datetime.fromisoformat(control_value["observation_boundary"]),
        tuple(
            DailyControlProbableIdentity(
                V1Setup(item["setup"]),
                V1Direction(item["direction"]),
            )
            for item in control_value.get("probable_identities", ())
        ),
    )
    return ShadowInstrumentAssessment(
        run_identity=value["run_identity"],
        provider_source_identity=value["provider_source_identity"],
        canonical_instrument=value["canonical_instrument"],
        control=control,
        weekly=_timeframe(value["weekly"]),
        daily=_timeframe(value["daily"]),
        four_hour=_timeframe(value["four_hour"]),
        one_hour=_timeframe(value["one_hour"]),
        state=ShadowCandidateState(value["state"]),
        setup=None if value["setup"] is None else V1Setup(value["setup"]),
        direction=V1Direction(value["direction"]),
        primary_reason=value["primary_reason"],
        contradictions=tuple(value["contradictions"]),
        session_remainder_dependent_change=value["session_remainder_dependent_change"],
        sponsor_observation=value["sponsor_observation"],
        eventual_market_development=value["eventual_market_development"],
        policy_identity=value["policy_identity"],
        authority=value["authority"],
    )


def _timeframe(value: object) -> TimeframeStructuralEvidence:
    if type(value) is not dict:
        raise ValueError("SHADOW_VALIDATION_RUN_INVALID")
    return TimeframeStructuralEvidence(
        ShadowTimeframe(value["timeframe"]),
        datetime.fromisoformat(value["observation_boundary"]),
        StructuralState(value["structure"]),
        None if value["setup"] is None else V1Setup(value["setup"]),
        V1Direction(value["direction"]),
        value["reason"],
        tuple(value["relevant_levels"]),
        value["participation"],
        value["completed"],
        value["session_remainder_participated"],
    )


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with temporary.open("w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "AnalyticalClaimEvidence",
    "DEFAULT_SHADOW_VALIDATION_EVIDENCE_ROOT",
    "NextConditionAuthority",
    "NextConditionEvidence",
    "NumericLevelAvailability",
    "NumericReferenceEvidence",
    "ReviewNumericEvidenceBundle",
    "ShadowValidationEvidenceStore",
    "SponsorValidationObservation",
]
