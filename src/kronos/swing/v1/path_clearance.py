"""KR-370-E01 deterministic 1H path-clearance machine evidence only."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
import re

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.models import PivotCandidate, PivotKind, V1Direction
from kronos.swing.v1.mtf_facts import (
    FactualTimeframe,
    InstrumentMtfFactSnapshot,
    ONE_HOUR_ATR_POLICY_IDENTITY,
    ONE_HOUR_ATR_POLICY_VERSION,
    OneHourAtrAvailability,
)


PATH_CLEARANCE_POLICY_IDENTITY = "KR-370-E01-IMMEDIATE-PATH-CLEARANCE-POLICY"
PATH_CLEARANCE_POLICY_VERSION = "1"
PATH_CLEARANCE_SCHEMA = "KRONOS-1H-PATH-CLEARANCE-FACT-V1"
PATH_CLEARANCE_AUTHORITY = (
    "MACHINE_EVIDENCE_ONLY_NO_PROMOTION_WATCH_OR_EXECUTION_AUTHORITY"
)
PATH_CLEARANCE_NEAR_ATR_MULTIPLE = 0.5


class PathClearanceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class PathObstacleSource(StrEnum):
    ONE_HOUR_SMA200 = "ONE_HOUR_SMA200"
    ONE_HOUR_STRUCTURAL_PIVOT_RADIUS_1 = "ONE_HOUR_STRUCTURAL_PIVOT_RADIUS_1"
    ONE_HOUR_STRUCTURAL_PIVOT_RADIUS_2 = "ONE_HOUR_STRUCTURAL_PIVOT_RADIUS_2"


@dataclass(frozen=True, slots=True)
class PathObstacleComponent:
    source: PathObstacleSource
    definition_identity: str
    level: float
    distance: float
    distance_atr14: float
    source_timestamp: datetime

    def __post_init__(self) -> None:
        if (
            type(self.source) is not PathObstacleSource
            or not self.definition_identity
            or any(
                type(item) is not float or not math.isfinite(item) or item < 0.0
                for item in (self.level, self.distance, self.distance_atr14)
            )
            or not _aware(self.source_timestamp)
        ):
            raise ValueError("PATH_OBSTACLE_COMPONENT_INVALID")


@dataclass(frozen=True, slots=True)
class OneHourPathClearanceFact:
    run_identity: str
    canonical_instrument: str
    direction: V1Direction
    analysis_boundary: datetime
    observation_boundary: datetime
    source_market_data_boundary: datetime
    completed_price: float
    atr14: float | None
    atr_fact_integrity_sha256: str
    available_sources: tuple[PathObstacleSource, ...]
    blocking_obstacles: tuple[PathObstacleComponent, ...]
    availability: PathClearanceAvailability
    unavailable_reason: str | None
    path_clear: bool | None
    clearance_level: float | None
    integrity_sha256: str
    atr_policy_identity: str = ONE_HOUR_ATR_POLICY_IDENTITY
    atr_policy_version: str = ONE_HOUR_ATR_POLICY_VERSION
    near_atr_multiple: float = PATH_CLEARANCE_NEAR_ATR_MULTIPLE
    policy_identity: str = PATH_CLEARANCE_POLICY_IDENTITY
    policy_version: str = PATH_CLEARANCE_POLICY_VERSION
    authority: str = PATH_CLEARANCE_AUTHORITY
    schema: str = PATH_CLEARANCE_SCHEMA

    def __post_init__(self) -> None:
        available = self.availability is PathClearanceAvailability.AVAILABLE
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or not re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument)
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not _aware(self.analysis_boundary)
            or not _aware(self.observation_boundary)
            or not _aware(self.source_market_data_boundary)
            or type(self.completed_price) is not float
            or not math.isfinite(self.completed_price)
            or self.completed_price < 0.0
            or (
                self.atr14 is not None
                and (
                    type(self.atr14) is not float
                    or not math.isfinite(self.atr14)
                    or self.atr14 < 0.0
                )
            )
            or re.fullmatch(r"[0-9a-f]{64}", self.atr_fact_integrity_sha256)
            is None
            or type(self.available_sources) is not tuple
            or len(set(self.available_sources)) != len(self.available_sources)
            or any(type(item) is not PathObstacleSource for item in self.available_sources)
            or type(self.blocking_obstacles) is not tuple
            or any(
                type(item) is not PathObstacleComponent
                for item in self.blocking_obstacles
            )
            or (
                available
                and (
                    self.atr14 is None
                    or self.atr14 <= 0.0
                    or not self.available_sources
                    or self.unavailable_reason is not None
                    or type(self.path_clear) is not bool
                    or (
                        self.path_clear
                        and (
                            self.blocking_obstacles
                            or self.clearance_level is not None
                        )
                    )
                    or (
                        not self.path_clear
                        and (
                            not self.blocking_obstacles
                            or type(self.clearance_level) is not float
                        )
                    )
                )
            )
            or (
                not available
                and (
                    not self.unavailable_reason
                    or self.path_clear is not None
                    or self.clearance_level is not None
                    or self.blocking_obstacles
                )
            )
            or self.atr_policy_identity != ONE_HOUR_ATR_POLICY_IDENTITY
            or self.atr_policy_version != ONE_HOUR_ATR_POLICY_VERSION
            or self.near_atr_multiple != PATH_CLEARANCE_NEAR_ATR_MULTIPLE
            or self.policy_identity != PATH_CLEARANCE_POLICY_IDENTITY
            or self.policy_version != PATH_CLEARANCE_POLICY_VERSION
            or self.authority != PATH_CLEARANCE_AUTHORITY
            or self.schema != PATH_CLEARANCE_SCHEMA
            or re.fullmatch(r"[0-9a-f]{64}", self.integrity_sha256) is None
            or self.integrity_sha256 != path_clearance_integrity_sha256(self)
        ):
            raise ValueError("ONE_HOUR_PATH_CLEARANCE_FACT_INVALID")


def evaluate_one_hour_path_clearance(
    *,
    run_identity: str,
    instrument: InstrumentMtfFactSnapshot,
    direction: V1Direction,
) -> OneHourPathClearanceFact:
    """Evaluate factual K3 support without producing a KR-370 criterion/state."""

    if (
        not is_swing_analysis_run_id(run_identity)
        or type(instrument) is not InstrumentMtfFactSnapshot
        or direction not in {V1Direction.LONG, V1Direction.SHORT}
    ):
        raise ValueError("PATH_CLEARANCE_REQUEST_INVALID")
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    atr = instrument.one_hour_atr
    if atr is None:
        return _unavailable(
            run_identity, instrument, direction, hour,
            "COMPLETED_1H_ATR14_FACT_UNAVAILABLE", "0" * 64,
        )
    if atr.run_identity != run_identity:
        raise ValueError("PATH_CLEARANCE_RUN_BINDING_INVALID")
    if atr.availability is not OneHourAtrAvailability.AVAILABLE:
        return _unavailable(
            run_identity, instrument, direction, hour,
            atr.unavailable_reason or "COMPLETED_1H_ATR14_UNAVAILABLE",
            atr.integrity_sha256,
        )
    if atr.value is None or atr.value <= 0.0:
        return _unavailable(
            run_identity, instrument, direction, hour,
            "COMPLETED_1H_ATR14_NON_POSITIVE", atr.integrity_sha256,
        )

    sources, candidates = _authoritative_obstacles(hour, direction)
    if not sources:
        return _unavailable(
            run_identity, instrument, direction, hour,
            "NO_AUTHORITATIVE_1H_OBSTACLE_SOURCE", atr.integrity_sha256,
        )
    blockers = tuple(
        PathObstacleComponent(
            source=source,
            definition_identity=definition,
            level=level,
            distance=abs(level - hour.close),
            distance_atr14=abs(level - hour.close) / atr.value,
            source_timestamp=timestamp,
        )
        for source, definition, level, timestamp in candidates
        if abs(level - hour.close) <= PATH_CLEARANCE_NEAR_ATR_MULTIPLE * atr.value
    )
    clearance = (
        None
        if not blockers
        else max(item.level for item in blockers)
        if direction is V1Direction.LONG
        else min(item.level for item in blockers)
    )
    return _fact(
        run_identity=run_identity,
        canonical_instrument=instrument.canonical_instrument,
        direction=direction,
        analysis_boundary=atr.analysis_boundary,
        observation_boundary=hour.observation_boundary,
        source_market_data_boundary=hour.source_market_data_boundary,
        completed_price=hour.close,
        atr14=atr.value,
        atr_fact_integrity_sha256=atr.integrity_sha256,
        available_sources=sources,
        blocking_obstacles=blockers,
        availability=PathClearanceAvailability.AVAILABLE,
        unavailable_reason=None,
        path_clear=not blockers,
        clearance_level=clearance,
    )


def _authoritative_obstacles(
    hour: object, direction: V1Direction
) -> tuple[
    tuple[PathObstacleSource, ...],
    tuple[tuple[PathObstacleSource, str, float, datetime], ...],
]:
    result: list[tuple[PathObstacleSource, str, float, datetime]] = []
    available: list[PathObstacleSource] = []
    moving_averages = getattr(hour, "moving_averages")
    if moving_averages is not None and moving_averages.sma200 is not None:
        available.append(PathObstacleSource.ONE_HOUR_SMA200)
        value = moving_averages.sma200
        if _adverse(value, hour.close, direction):
            result.append((
                PathObstacleSource.ONE_HOUR_SMA200,
                "ARITHMETIC_MEAN_LAST_200_COMPLETED_1H_CLOSES",
                value,
                hour.observation_boundary,
            ))
    for series in hour.structural_measurements:
        source = (
            PathObstacleSource.ONE_HOUR_STRUCTURAL_PIVOT_RADIUS_1
            if series.radius == 1
            else PathObstacleSource.ONE_HOUR_STRUCTURAL_PIVOT_RADIUS_2
        )
        pivots: tuple[PivotCandidate, ...] = (
            series.swing_highs
            if direction is V1Direction.LONG
            else series.swing_lows
        )
        expected_kind = (
            PivotKind.HIGH if direction is V1Direction.LONG else PivotKind.LOW
        )
        if pivots:
            available.append(source)
        for pivot in pivots:
            if pivot.kind is not expected_kind:
                raise ValueError("PATH_CLEARANCE_PIVOT_KIND_INVALID")
            if _adverse(pivot.value, hour.close, direction):
                result.append((
                    source, series.definition_identity, pivot.value,
                    pivot.timestamp,
                ))
    return tuple(dict.fromkeys(available)), tuple(result)


def _adverse(level: float, price: float, direction: V1Direction) -> bool:
    return level > price if direction is V1Direction.LONG else level < price


def _unavailable(
    run_identity: str,
    instrument: InstrumentMtfFactSnapshot,
    direction: V1Direction,
    hour: object,
    reason: str,
    atr_integrity: str,
) -> OneHourPathClearanceFact:
    return _fact(
        run_identity=run_identity,
        canonical_instrument=instrument.canonical_instrument,
        direction=direction,
        analysis_boundary=(
            instrument.one_hour_atr.analysis_boundary
            if instrument.one_hour_atr is not None
            else hour.observation_boundary
        ),
        observation_boundary=hour.observation_boundary,
        source_market_data_boundary=hour.source_market_data_boundary,
        completed_price=hour.close,
        atr14=(
            None
            if instrument.one_hour_atr is None
            else instrument.one_hour_atr.value
        ),
        atr_fact_integrity_sha256=atr_integrity,
        available_sources=(),
        blocking_obstacles=(),
        availability=PathClearanceAvailability.UNAVAILABLE,
        unavailable_reason=reason,
        path_clear=None,
        clearance_level=None,
    )


def _fact(**values: object) -> OneHourPathClearanceFact:
    return OneHourPathClearanceFact(
        **values,  # type: ignore[arg-type]
        integrity_sha256=path_clearance_integrity_sha256(values),
    )


def path_clearance_integrity_sha256(
    fact: OneHourPathClearanceFact | dict[str, object],
) -> str:
    material = (
        asdict(fact)
        if type(fact) is OneHourPathClearanceFact
        else dict(fact)
    )
    material.pop("integrity_sha256", None)
    material.setdefault("atr_policy_identity", ONE_HOUR_ATR_POLICY_IDENTITY)
    material.setdefault("atr_policy_version", ONE_HOUR_ATR_POLICY_VERSION)
    material.setdefault("near_atr_multiple", PATH_CLEARANCE_NEAR_ATR_MULTIPLE)
    material.setdefault("policy_identity", PATH_CLEARANCE_POLICY_IDENTITY)
    material.setdefault("policy_version", PATH_CLEARANCE_POLICY_VERSION)
    material.setdefault("authority", PATH_CLEARANCE_AUTHORITY)
    material.setdefault("schema", PATH_CLEARANCE_SCHEMA)
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
    "OneHourPathClearanceFact", "PATH_CLEARANCE_AUTHORITY",
    "PATH_CLEARANCE_NEAR_ATR_MULTIPLE", "PATH_CLEARANCE_POLICY_IDENTITY",
    "PATH_CLEARANCE_POLICY_VERSION", "PATH_CLEARANCE_SCHEMA",
    "PathClearanceAvailability", "PathObstacleComponent",
    "PathObstacleSource", "evaluate_one_hour_path_clearance",
    "path_clearance_integrity_sha256",
]
