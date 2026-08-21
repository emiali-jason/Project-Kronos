"""KR-370-E03 deterministic completed-1H extension evidence only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
import re

from kronos.swing.v1.models import PivotCandidate, PivotKind, V1Direction
from kronos.swing.v1.mtf_facts import (
    FactualPivotSeries,
    FactualTimeframe,
    ONE_HOUR_ATR_POLICY_IDENTITY,
    ONE_HOUR_ATR_POLICY_VERSION,
    OneHourAtrAvailability,
    SameRunMtfFactSnapshot,
    one_hour_atr_integrity_sha256,
)
from kronos.swing.v1.native_readiness import (
    ConditionEvidence,
    DeterministicExtensionEvidence,
    LevelAvailability,
    NativeConditionInputs,
)
from kronos.swing.v1.native_review import NativeReviewRequirement


EXTENSION_POLICY_IDENTITY = "KR-370-E03-COMPLETED-1H-STRUCTURAL-EXTENSION-POLICY"
EXTENSION_POLICY_VERSION = "1"
EXTENSION_SCHEMA = "KRONOS-COMPLETED-1H-STRUCTURAL-EXTENSION-FACT-V1"
EXTENSION_AUTHORITY = "DETERMINISTIC_NUMERICAL_FACT_ONLY"
EXTENSION_PRODUCT = "SWING"
EXTENSION_THRESHOLD_ATR = 2.0
EXTENSION_PIVOT_HIERARCHY = (2, 1)
EXTENSION_PIVOT_HIERARCHY_IDENTITY = (
    "LATEST_DIRECTIONAL_RADIUS_2_THEN_LATEST_DIRECTIONAL_RADIUS_1"
)


class ExtensionAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class CompletedOneHourExtensionFact:
    """Bound K5 prerequisite fact with no KR-370 decision authority."""

    run_identity: str
    native_assessment_sha256: str
    canonical_instrument: str
    direction: V1Direction
    analysis_boundary: datetime
    observation_boundary: datetime
    source_market_data_boundary: datetime
    completed_close: float
    calendar_identity: str
    calendar_version: str
    session_identity: str
    exchange_timezone: str
    source_provider_identity: str
    provenance: tuple[str, ...]
    availability: ExtensionAvailability
    unavailable_reason: str | None
    pivot_definition_identity: str | None
    selected_pivot_radius: int | None
    selected_pivot_identity: str | None
    selected_pivot_boundary: datetime | None
    anchor_price: float | None
    atr14: float | None
    atr_fact_integrity_sha256: str
    directional_distance: float | None
    extension_atr: float | None
    materially_extended: bool | None
    integrity_sha256: str
    product: str = EXTENSION_PRODUCT
    timeframe: FactualTimeframe = FactualTimeframe.ONE_HOUR
    pivot_hierarchy_identity: str = EXTENSION_PIVOT_HIERARCHY_IDENTITY
    atr_policy_identity: str = ONE_HOUR_ATR_POLICY_IDENTITY
    atr_policy_version: str = ONE_HOUR_ATR_POLICY_VERSION
    threshold_atr: float = EXTENSION_THRESHOLD_ATR
    policy_identity: str = EXTENSION_POLICY_IDENTITY
    policy_version: str = EXTENSION_POLICY_VERSION
    authority: str = EXTENSION_AUTHORITY
    schema: str = EXTENSION_SCHEMA

    def __post_init__(self) -> None:
        available = self.availability is ExtensionAvailability.AVAILABLE
        pivot_bundle = (
            self.pivot_definition_identity,
            self.selected_pivot_radius,
            self.selected_pivot_identity,
            self.selected_pivot_boundary,
            self.anchor_price,
        )
        pivot_present = all(item is not None for item in pivot_bundle)
        pivot_absent = all(item is None for item in pivot_bundle)
        numeric_values = (
            self.completed_close,
            self.anchor_price,
            self.atr14,
            self.directional_distance,
            self.extension_atr,
        )
        if (
            re.fullmatch(r"SWING-RUN-[A-F0-9]{32}", self.run_identity) is None
            or re.fullmatch(r"[0-9a-f]{64}", self.native_assessment_sha256) is None
            or re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument) is None
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not all(_aware(item) for item in (
                self.analysis_boundary,
                self.observation_boundary,
                self.source_market_data_boundary,
            ))
            or self.observation_boundary > self.analysis_boundary
            or any(
                item is not None
                and (type(item) is not float or not math.isfinite(item))
                for item in numeric_values
            )
            or self.completed_close < 0.0
            or not all((
                self.calendar_identity,
                self.calendar_version,
                self.session_identity,
                self.source_provider_identity,
            ))
            or self.exchange_timezone != "Asia/Kolkata"
            or type(self.provenance) is not tuple
            or not self.provenance
            or type(self.availability) is not ExtensionAvailability
            or not (pivot_present or pivot_absent)
            or (
                pivot_present
                and (
                    type(self.selected_pivot_radius) is not int
                    or self.selected_pivot_radius not in EXTENSION_PIVOT_HIERARCHY
                    or not _aware(self.selected_pivot_boundary)
                    or self.anchor_price is None
                    or self.anchor_price < 0.0
                )
            )
            or re.fullmatch(r"[0-9a-f]{64}", self.atr_fact_integrity_sha256) is None
            or (
                self.directional_distance is not None
                and self.anchor_price is not None
                and self.directional_distance
                != _directional_distance(
                    self.completed_close, self.anchor_price, self.direction
                )
            )
            or (
                available
                and (
                    self.unavailable_reason is not None
                    or not pivot_present
                    or self.atr14 is None
                    or self.atr14 <= 0.0
                    or self.directional_distance is None
                    or self.directional_distance < 0.0
                    or self.extension_atr is None
                    or self.extension_atr
                    != self.directional_distance / self.atr14
                    or type(self.materially_extended) is not bool
                    or self.materially_extended
                    != (self.extension_atr > EXTENSION_THRESHOLD_ATR)
                )
            )
            or (
                not available
                and (
                    not self.unavailable_reason
                    or self.extension_atr is not None
                    or self.materially_extended is not None
                )
            )
            or self.product != EXTENSION_PRODUCT
            or self.timeframe is not FactualTimeframe.ONE_HOUR
            or self.pivot_hierarchy_identity
            != EXTENSION_PIVOT_HIERARCHY_IDENTITY
            or self.atr_policy_identity != ONE_HOUR_ATR_POLICY_IDENTITY
            or self.atr_policy_version != ONE_HOUR_ATR_POLICY_VERSION
            or self.threshold_atr != EXTENSION_THRESHOLD_ATR
            or self.policy_identity != EXTENSION_POLICY_IDENTITY
            or self.policy_version != EXTENSION_POLICY_VERSION
            or self.authority != EXTENSION_AUTHORITY
            or self.schema != EXTENSION_SCHEMA
            or re.fullmatch(r"[0-9a-f]{64}", self.integrity_sha256) is None
            or self.integrity_sha256 != extension_integrity_sha256(self)
        ):
            raise ValueError("COMPLETED_ONE_HOUR_EXTENSION_FACT_INVALID")


def evaluate_completed_one_hour_extension(
    requirement: NativeReviewRequirement,
    facts: SameRunMtfFactSnapshot,
) -> CompletedOneHourExtensionFact:
    """Evaluate the authorized E03 fact without producing a Sponsor state."""

    if (
        type(requirement) is not NativeReviewRequirement
        or type(facts) is not SameRunMtfFactSnapshot
        or facts.run_identity != requirement.native_run_identity
    ):
        raise ValueError("EXTENSION_SAME_RUN_BINDING_INVALID")
    instrument = facts.instrument(requirement.canonical_instrument)
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    thesis_hour = next(
        item
        for item in requirement.thesis.timeframe_facts
        if item.timeframe is FactualTimeframe.ONE_HOUR
    )
    if (
        thesis_hour.observation_boundary != hour.observation_boundary
        or thesis_hour.source_timestamp != hour.source_timestamp
        or thesis_hour.close != hour.close
        or thesis_hour.provider_identity != hour.source_provider_identity
        or thesis_hour.calendar_identity != hour.calendar_identity
        or thesis_hour.calendar_version != hour.calendar_version
        or thesis_hour.session_identity != hour.session_identity
    ):
        raise ValueError("EXTENSION_ASSESSMENT_BOUNDARY_BINDING_INVALID")
    if hour.source_interval != "60minute":
        return _unavailable(requirement, hour, "INCOMPLETE_1H_EVIDENCE")
    atr = instrument.one_hour_atr
    if atr is None:
        return _unavailable(
            requirement, hour, "COMPLETED_1H_ATR14_FACT_UNAVAILABLE"
        )
    if (
        atr.run_identity != requirement.native_run_identity
        or atr.canonical_instrument != requirement.canonical_instrument
        or atr.observation_boundary != hour.observation_boundary
        or atr.source_market_data_boundary != hour.source_market_data_boundary
    ):
        raise ValueError("EXTENSION_ATR_BINDING_INVALID")
    if atr.integrity_sha256 != one_hour_atr_integrity_sha256(atr):
        raise ValueError("EXTENSION_ATR_INTEGRITY_INVALID")
    if atr.availability is not OneHourAtrAvailability.AVAILABLE:
        return _unavailable(
            requirement,
            hour,
            atr.unavailable_reason or "COMPLETED_1H_ATR14_UNAVAILABLE",
            atr=atr,
        )
    if atr.value is None or atr.value <= 0.0:
        return _unavailable(
            requirement, hour, "COMPLETED_1H_ATR14_NON_POSITIVE", atr=atr
        )

    selected = _select_anchor(
        hour.structural_measurements,
        requirement.thesis.direction,
        hour.observation_boundary,
    )
    if selected is None:
        return _unavailable(
            requirement, hour, "REQUIRED_DIRECTIONAL_1H_PIVOT_UNAVAILABLE", atr=atr
        )
    series, pivot = selected
    distance = _directional_distance(
        hour.close, pivot.value, requirement.thesis.direction
    )
    if distance < 0.0:
        return _unavailable(
            requirement,
            hour,
            "DIRECTIONAL_DISTANCE_NEGATIVE",
            atr=atr,
            series=series,
            pivot=pivot,
            directional_distance=distance,
        )
    extension_atr = distance / atr.value
    return _fact(
        **_base_values(requirement, hour, atr=atr, series=series, pivot=pivot),
        availability=ExtensionAvailability.AVAILABLE,
        unavailable_reason=None,
        directional_distance=distance,
        extension_atr=extension_atr,
        materially_extended=extension_atr > EXTENSION_THRESHOLD_ATR,
    )


def extension_native_condition_inputs(
    fact: CompletedOneHourExtensionFact,
    requirement: NativeReviewRequirement,
) -> NativeConditionInputs:
    """Project one exact E03 fact into the existing V3 condition contract."""

    if (
        type(fact) is not CompletedOneHourExtensionFact
        or type(requirement) is not NativeReviewRequirement
        or fact.run_identity != requirement.native_run_identity
        or fact.native_assessment_sha256
        != requirement.thesis.native_assessment_sha256
        or fact.canonical_instrument != requirement.canonical_instrument
        or fact.direction is not requirement.thesis.direction
        or fact.integrity_sha256 != extension_integrity_sha256(fact)
    ):
        raise ValueError("EXTENSION_NATIVE_INPUT_BINDING_INVALID")
    available = fact.availability is ExtensionAvailability.AVAILABLE
    context = ConditionEvidence(
        condition_identity="KR_370_E03_EXTENSION",
        source_evidence_ids=(
            fact.native_assessment_sha256,
            fact.atr_fact_integrity_sha256,
            fact.integrity_sha256,
        ),
        timeframe=FactualTimeframe.ONE_HOUR,
        reference_identity=(fact.selected_pivot_identity if available else None),
        level_availability=(
            LevelAvailability.AVAILABLE
            if available
            else LevelAvailability.LEVEL_UNAVAILABLE
        ),
        price=(fact.anchor_price if available else None),
        zone_low=None,
        zone_high=None,
        observation_boundary=fact.observation_boundary,
        reason_code=(
            "MATERIALLY_EXTENDED"
            if fact.materially_extended is True
            else "NOT_MATERIALLY_EXTENDED"
            if fact.materially_extended is False
            else fact.unavailable_reason or "EXTENSION_UNAVAILABLE"
        ),
        provenance=tuple(dict.fromkeys((
            *fact.provenance,
            f"{fact.policy_identity}/{fact.policy_version}",
            f"{fact.atr_policy_identity}/{fact.atr_policy_version}",
            fact.integrity_sha256,
        ))),
    )
    return NativeConditionInputs(
        extension=DeterministicExtensionEvidence(
            context,
            fact.materially_extended is True,
        )
    )


def _select_anchor(
    measurements: tuple[FactualPivotSeries, ...],
    direction: V1Direction,
    observation_boundary: datetime,
) -> tuple[FactualPivotSeries, PivotCandidate] | None:
    expected = PivotKind.LOW if direction is V1Direction.LONG else PivotKind.HIGH
    for radius in EXTENSION_PIVOT_HIERARCHY:
        series = next((item for item in measurements if item.radius == radius), None)
        if series is None:
            continue
        candidates = tuple(
            item
            for item in (
                series.swing_lows
                if expected is PivotKind.LOW
                else series.swing_highs
            )
            if item.timestamp <= observation_boundary
        )
        if any(item.kind is not expected for item in candidates):
            raise ValueError("EXTENSION_PIVOT_KIND_INVALID")
        if candidates:
            return series, max(
                candidates, key=lambda item: (item.timestamp, item.candle_index)
            )
    return None


def _directional_distance(
    close: float, anchor: float, direction: V1Direction
) -> float:
    return close - anchor if direction is V1Direction.LONG else anchor - close


def _unavailable(
    requirement: NativeReviewRequirement,
    hour: object,
    reason: str,
    *,
    atr: object | None = None,
    series: FactualPivotSeries | None = None,
    pivot: PivotCandidate | None = None,
    directional_distance: float | None = None,
) -> CompletedOneHourExtensionFact:
    return _fact(
        **_base_values(requirement, hour, atr=atr, series=series, pivot=pivot),
        availability=ExtensionAvailability.UNAVAILABLE,
        unavailable_reason=reason,
        directional_distance=directional_distance,
        extension_atr=None,
        materially_extended=None,
    )


def _base_values(
    requirement: NativeReviewRequirement,
    hour: object,
    *,
    atr: object | None,
    series: FactualPivotSeries | None,
    pivot: PivotCandidate | None,
) -> dict[str, object]:
    return {
        "run_identity": requirement.native_run_identity,
        "native_assessment_sha256": requirement.thesis.native_assessment_sha256,
        "canonical_instrument": requirement.canonical_instrument,
        "direction": requirement.thesis.direction,
        # E03 is evaluated against the governed completed-1H fact.  Its
        # observation boundary is therefore the same-run analytical boundary
        # that can authoritatively include that completed bucket.  The E01 ATR
        # fact remains bound below by immutable integrity identity; its older
        # daily analysis boundary is not E03's boundary authority.
        "analysis_boundary": getattr(hour, "observation_boundary"),
        "observation_boundary": getattr(hour, "observation_boundary"),
        "source_market_data_boundary": getattr(
            hour, "source_market_data_boundary"
        ),
        "completed_close": getattr(hour, "close"),
        "calendar_identity": getattr(hour, "calendar_identity"),
        "calendar_version": getattr(hour, "calendar_version"),
        "session_identity": getattr(hour, "session_identity"),
        "exchange_timezone": getattr(hour, "exchange_timezone"),
        "source_provider_identity": getattr(hour, "source_provider_identity"),
        "provenance": tuple(getattr(hour, "provenance")),
        "pivot_definition_identity": (
            None if series is None else series.definition_identity
        ),
        "selected_pivot_radius": None if series is None else series.radius,
        "selected_pivot_identity": (
            None
            if series is None or pivot is None
            else (
                f"{series.definition_identity}@{pivot.kind.value}@"
                f"{pivot.candle_index}@{pivot.timestamp.isoformat()}"
            )
        ),
        "selected_pivot_boundary": None if pivot is None else pivot.timestamp,
        "anchor_price": None if pivot is None else pivot.value,
        "atr14": None if atr is None else getattr(atr, "value"),
        "atr_fact_integrity_sha256": (
            "0" * 64 if atr is None else getattr(atr, "integrity_sha256")
        ),
    }


def _fact(**values: object) -> CompletedOneHourExtensionFact:
    return CompletedOneHourExtensionFact(
        **values,  # type: ignore[arg-type]
        integrity_sha256=extension_integrity_sha256(values),
    )


def extension_integrity_sha256(
    fact: CompletedOneHourExtensionFact | dict[str, object],
) -> str:
    material = (
        asdict(fact)
        if type(fact) is CompletedOneHourExtensionFact
        else dict(fact)
    )
    material.pop("integrity_sha256", None)
    material.setdefault("product", EXTENSION_PRODUCT)
    material.setdefault("timeframe", FactualTimeframe.ONE_HOUR)
    material.setdefault(
        "pivot_hierarchy_identity", EXTENSION_PIVOT_HIERARCHY_IDENTITY
    )
    material.setdefault("atr_policy_identity", ONE_HOUR_ATR_POLICY_IDENTITY)
    material.setdefault("atr_policy_version", ONE_HOUR_ATR_POLICY_VERSION)
    material.setdefault("threshold_atr", EXTENSION_THRESHOLD_ATR)
    material.setdefault("policy_identity", EXTENSION_POLICY_IDENTITY)
    material.setdefault("policy_version", EXTENSION_POLICY_VERSION)
    material.setdefault("authority", EXTENSION_AUTHORITY)
    material.setdefault("schema", EXTENSION_SCHEMA)
    return sha256(
        json.dumps(
            _json_value(material), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _json_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "CompletedOneHourExtensionFact",
    "EXTENSION_AUTHORITY",
    "EXTENSION_PIVOT_HIERARCHY",
    "EXTENSION_PIVOT_HIERARCHY_IDENTITY",
    "EXTENSION_POLICY_IDENTITY",
    "EXTENSION_POLICY_VERSION",
    "EXTENSION_SCHEMA",
    "EXTENSION_THRESHOLD_ATR",
    "ExtensionAvailability",
    "evaluate_completed_one_hour_extension",
    "extension_integrity_sha256",
    "extension_native_condition_inputs",
]
