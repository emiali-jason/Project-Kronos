"""Immutable, factual same-run MTF evidence with no discovery authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json
import math
import os
from pathlib import Path
import re
from threading import RLock

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.models import PivotCandidate, PivotKind
from kronos.swing.v1.reference_facts import (
    SwingReferenceChartTimeframe,
    SwingReferenceCprMachineFact,
    reference_machine_fact_from_dict,
)
from kronos.swing.v1.weekly_facts import (
    CompletedWeeklyBarFact,
    FactualPivotRelation,
    FactualPriceRelation,
    FactualStructureCondition,
    HistoricalDayRequestWindowFact,
    NseWeeklyFactualFoundation,
    WeeklyFactAvailability,
    WeeklyPivotFacts,
    WeeklySmaDirection,
)


MTF_FACT_SNAPSHOT_SCHEMA = "KRONOS-CURRENT-GOVERNED-MTF-FACTS-V1"
MTF_FACT_AUTHORITY = "FACTUAL_ONLY_NO_CANDIDATE_AUTHORITY"
QUOTE_FACT_AUTHORITY = "FACTUAL_ONLY_SEPARATE_NOT_ACQUIRED"
DEFAULT_MTF_FACT_EVIDENCE_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "swing-v1"
    / "current-governed-mtf"
)


class FactualTimeframe(StrEnum):
    WEEKLY = "1W"
    DAILY = "1D"
    FOUR_HOUR = "4H"
    ONE_HOUR = "1H"


@dataclass(frozen=True, slots=True)
class FactualPivotSeries:
    """One measured pivot series; no preferred definition or consensus exists."""

    definition_identity: str
    radius: int
    swing_highs: tuple[PivotCandidate, ...]
    swing_lows: tuple[PivotCandidate, ...]

    def __post_init__(self) -> None:
        if (
            self.definition_identity
            != f"FRACTAL_UNIQUE_EXTREME_RADIUS_{self.radius}"
            or self.radius not in {1, 2}
            or type(self.swing_highs) is not tuple
            or type(self.swing_lows) is not tuple
            or any(item.kind is not PivotKind.HIGH for item in self.swing_highs)
            or any(item.kind is not PivotKind.LOW for item in self.swing_lows)
        ):
            raise ValueError("MTF_FACT_PIVOT_SERIES_INVALID")


@dataclass(frozen=True, slots=True)
class FactualMovingAverageFacts:
    """Exact completed-series moving averages; interpretation belongs elsewhere."""

    completed_count: int
    sma20: float | None
    sma50: float | None
    sma200: float | None
    prior_sma20_5bars: float | None
    prior_sma50_5bars: float | None
    prior_sma200_5bars: float | None

    def __post_init__(self) -> None:
        values = (
            self.sma20, self.sma50, self.sma200,
            self.prior_sma20_5bars, self.prior_sma50_5bars,
            self.prior_sma200_5bars,
        )
        if (
            type(self.completed_count) is not int
            or self.completed_count < 0
            or any(
                item is not None
                and (type(item) is not float or not math.isfinite(item))
                for item in values
            )
        ):
            raise ValueError("MTF_FACT_MOVING_AVERAGES_INVALID")


@dataclass(frozen=True, slots=True)
class FactualVolumeFacts:
    """Traded-volume measurements with no participation classification."""

    current: int
    prior_20_mean: float | None
    authority: str = "FACTUAL_EXPLANATORY_ONLY"

    def __post_init__(self) -> None:
        if (
            type(self.current) is not int
            or self.current < 0
            or (
                self.prior_20_mean is not None
                and (
                    type(self.prior_20_mean) is not float
                    or not math.isfinite(self.prior_20_mean)
                    or self.prior_20_mean < 0.0
                )
            )
            or self.authority != "FACTUAL_EXPLANATORY_ONLY"
        ):
            raise ValueError("MTF_FACT_VOLUME_INVALID")


@dataclass(frozen=True, slots=True)
class CompletedTimeframeFact:
    """Latest completed governed OHLCV fact for one timeframe."""

    timeframe: FactualTimeframe
    observation_boundary: datetime
    source_timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    calendar_identity: str
    calendar_version: str
    session_identity: str
    exchange_timezone: str
    source_interval: str
    source_provider_identity: str
    source_market_data_boundary: datetime
    provenance: tuple[str, ...]
    structural_measurements: tuple[FactualPivotSeries, ...]
    moving_averages: FactualMovingAverageFacts | None = None
    volume_facts: FactualVolumeFacts | None = None
    bucket_class: str | None = None
    authority: str = MTF_FACT_AUTHORITY

    def __post_init__(self) -> None:
        prices = (self.open, self.high, self.low, self.close)
        if (
            type(self.timeframe) is not FactualTimeframe
            or not _aware(self.observation_boundary)
            or not _aware(self.source_timestamp)
            or self.source_timestamp > self.observation_boundary
            or any(type(item) is not float or not math.isfinite(item) or item < 0.0 for item in prices)
            or self.high < max(self.open, self.low, self.close)
            or self.low > min(self.open, self.high, self.close)
            or type(self.volume) is not int
            or self.volume < 0
            or not self.calendar_identity
            or not self.calendar_version
            or not self.session_identity
            or self.exchange_timezone != "Asia/Kolkata"
            or self.source_interval not in {"DAY", "60minute"}
            or not self.source_provider_identity
            or not _aware(self.source_market_data_boundary)
            or not self.provenance
            or type(self.structural_measurements) is not tuple
            or tuple(item.radius for item in self.structural_measurements) != (1, 2)
            or self.authority != MTF_FACT_AUTHORITY
            or (
                self.moving_averages is not None
                and type(self.moving_averages) is not FactualMovingAverageFacts
            )
            or (
                self.volume_facts is not None
                and type(self.volume_facts) is not FactualVolumeFacts
            )
            or (
                self.timeframe is FactualTimeframe.FOUR_HOUR
                and self.bucket_class not in {"FULL_DURATION", "SESSION_REMAINDER"}
            )
            or (
                self.timeframe is not FactualTimeframe.FOUR_HOUR
                and self.bucket_class is not None
            )
        ):
            raise ValueError("COMPLETED_TIMEFRAME_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class InstrumentMtfFactSnapshot:
    canonical_instrument: str
    exchange: str
    timeframes: tuple[CompletedTimeframeFact, ...]
    nse_weekly_foundation: NseWeeklyFactualFoundation | None = None
    reference_facts: tuple[SwingReferenceCprMachineFact, ...] = ()

    def __post_init__(self) -> None:
        if (
            not re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument)
            or self.exchange not in {"NSE", "MCX"}
            or type(self.timeframes) is not tuple
            or tuple(item.timeframe for item in self.timeframes)
            != tuple(FactualTimeframe)
            or (
                self.exchange == "MCX"
                and self.nse_weekly_foundation is not None
            )
            or (
                self.nse_weekly_foundation is not None
                and self.nse_weekly_foundation.canonical_instrument
                != self.canonical_instrument
            )
            or type(self.reference_facts) is not tuple
            or (
                self.reference_facts
                and tuple(item.chart_timeframe for item in self.reference_facts)
                != tuple(SwingReferenceChartTimeframe)
            )
            or any(
                item.canonical_instrument != self.canonical_instrument
                for item in self.reference_facts
            )
        ):
            raise ValueError("INSTRUMENT_MTF_FACT_SNAPSHOT_INVALID")

    def fact(self, timeframe: FactualTimeframe) -> CompletedTimeframeFact:
        return next(item for item in self.timeframes if item.timeframe is timeframe)

    def reference_fact(
        self, timeframe: SwingReferenceChartTimeframe
    ) -> SwingReferenceCprMachineFact:
        try:
            return next(
                item for item in self.reference_facts
                if item.chart_timeframe is timeframe
            )
        except StopIteration as error:
            raise ValueError("SWING_REFERENCE_FACT_UNAVAILABLE") from error


@dataclass(frozen=True, slots=True)
class SameRunMtfFactSnapshot:
    """Complete same-98 factual MTF snapshot, independent of all classifiers."""

    run_identity: str
    observed_at: datetime
    provider_source_identity: str
    instruments: tuple[InstrumentMtfFactSnapshot, ...]
    quote_context: None = None
    quote_authority: str = QUOTE_FACT_AUTHORITY
    authority: str = MTF_FACT_AUTHORITY
    schema: str = MTF_FACT_SNAPSHOT_SCHEMA

    def __post_init__(self) -> None:
        identities = tuple(item.canonical_instrument for item in self.instruments)
        reference_counts = {len(item.reference_facts) for item in self.instruments}
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or not _aware(self.observed_at)
            or not self.provider_source_identity.startswith("KITE-MTF-FACTS-")
            or len(self.provider_source_identity) != len("KITE-MTF-FACTS-") + 64
            or type(self.instruments) is not tuple
            or len(self.instruments) != 98
            or len(set(identities)) != 98
            or reference_counts not in ({0}, {4})
            or any(
                fact.run_identity != self.run_identity
                for instrument in self.instruments
                for fact in instrument.reference_facts
            )
            or self.quote_context is not None
            or self.quote_authority != QUOTE_FACT_AUTHORITY
            or self.authority != MTF_FACT_AUTHORITY
            or self.schema != MTF_FACT_SNAPSHOT_SCHEMA
        ):
            raise ValueError("SAME_RUN_MTF_FACT_SNAPSHOT_INVALID")

    def instrument(self, canonical_identity: str) -> InstrumentMtfFactSnapshot:
        try:
            return next(
                item for item in self.instruments
                if item.canonical_instrument == canonical_identity
            )
        except StopIteration as error:
            raise ValueError("MTF_FACT_INSTRUMENT_UNAVAILABLE") from error


class MtfFactEvidenceStore:
    """Atomic restart-safe store for complete immutable factual snapshots."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("MTF_FACT_STORE_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, snapshot: SameRunMtfFactSnapshot) -> Path:
        if type(snapshot) is not SameRunMtfFactSnapshot:
            raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
        path = self._path(snapshot.run_identity)
        payload = {"schema": MTF_FACT_SNAPSHOT_SCHEMA, "snapshot": _json_value(asdict(snapshot))}
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("MTF_FACT_SNAPSHOT_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load(self, run_identity: str) -> SameRunMtfFactSnapshot:
        with self._lock:
            payload = _read(self._path(run_identity))
        if payload.get("schema") != MTF_FACT_SNAPSHOT_SCHEMA:
            raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
        return _snapshot(payload.get("snapshot"))

    def latest(self) -> SameRunMtfFactSnapshot | None:
        """Return the newest immutable factual snapshot, if one exists."""

        directory = self._root / "complete-runs"
        with self._lock:
            if not directory.exists():
                return None
            snapshots = []
            for path in directory.glob("SWING-RUN-*.json"):
                try:
                    payload = _read(path)
                    if payload.get("schema") == MTF_FACT_SNAPSHOT_SCHEMA:
                        snapshots.append(_snapshot(payload.get("snapshot")))
                except ValueError:
                    continue
        return max(snapshots, key=lambda item: item.observed_at, default=None)

    def _path(self, run_identity: str) -> Path:
        if not is_swing_analysis_run_id(run_identity):
            raise ValueError("MTF_FACT_RUN_IDENTITY_INVALID")
        return self._root / "complete-runs" / f"{run_identity}.json"


def _snapshot(value: object) -> SameRunMtfFactSnapshot:
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    try:
        instruments = tuple(_instrument(item) for item in value["instruments"])
        return SameRunMtfFactSnapshot(
            run_identity=value["run_identity"],
            observed_at=datetime.fromisoformat(value["observed_at"]),
            provider_source_identity=value["provider_source_identity"],
            instruments=instruments,
            quote_context=value["quote_context"],
            quote_authority=value["quote_authority"],
            authority=value["authority"],
            schema=value["schema"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID") from error


def _instrument(value: object) -> InstrumentMtfFactSnapshot:
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return InstrumentMtfFactSnapshot(
        value["canonical_instrument"],
        value["exchange"],
        tuple(_timeframe(item) for item in value["timeframes"]),
        (
            None
            if value.get("nse_weekly_foundation") is None
            else _weekly_foundation(value["nse_weekly_foundation"])
        ),
        tuple(
            reference_machine_fact_from_dict(item)
            for item in value.get("reference_facts", ())
        ),
    )


def _weekly_foundation(value: object) -> NseWeeklyFactualFoundation:
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return NseWeeklyFactualFoundation(
        canonical_instrument=value["canonical_instrument"],
        provider=value["provider"],
        provider_exchange=value["provider_exchange"],
        provider_segment=value["provider_segment"],
        provider_trading_symbol=value["provider_trading_symbol"],
        provider_instrument_type=value["provider_instrument_type"],
        run_identity=value["run_identity"],
        availability=WeeklyFactAvailability(value["availability"]),
        unavailable_reason=value["unavailable_reason"],
        request_windows=tuple(_request_window(item) for item in value["request_windows"]),
        source_interval=value["source_interval"],
        calendar_identity=value["calendar_identity"],
        calendar_version=value["calendar_version"],
        calendar_publication_sha256=value["calendar_publication_sha256"],
        predecessor_source_result_sha256=value["predecessor_source_result_sha256"],
        completed_weekly_bars=tuple(_weekly_bar(item) for item in value["completed_weekly_bars"]),
        current_sma200=value["current_sma200"],
        prior_sma200_5w=value["prior_sma200_5w"],
        sma200_difference=value["sma200_difference"],
        sma200_direction=(
            None if value["sma200_direction"] is None
            else WeeklySmaDirection(value["sma200_direction"])
        ),
        latest_weekly_close=value["latest_weekly_close"],
        latest_close_relation=(
            None if value["latest_close_relation"] is None
            else FactualPriceRelation(value["latest_close_relation"])
        ),
        radius_2_structure=_weekly_pivots(value["radius_2_structure"]),
        radius_1_developing=_weekly_pivots(value["radius_1_developing"]),
        observation_boundary=(
            None if value["observation_boundary"] is None
            else datetime.fromisoformat(value["observation_boundary"])
        ),
        source_result_sha256=value["source_result_sha256"],
        authority=value["authority"],
        schema=value["schema"],
    )


def _request_window(value: object) -> HistoricalDayRequestWindowFact:
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return HistoricalDayRequestWindowFact(
        datetime.fromisoformat(value["start"]),
        datetime.fromisoformat(value["end"]),
        value["result_count"],
    )


def _weekly_bar(value: object) -> CompletedWeeklyBarFact:
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return CompletedWeeklyBarFact(
        value["trading_week_identity"],
        datetime.fromisoformat(value["observation_boundary"]),
        datetime.fromisoformat(value["source_start"]),
        value["open"], value["high"], value["low"], value["close"], value["volume"],
        tuple(value["constituent_identities"]),
        value["source_provider_identity"],
        datetime.fromisoformat(value["source_market_data_boundary"]),
        tuple(value["provenance"]),
    )


def _weekly_pivots(value: object) -> WeeklyPivotFacts | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return WeeklyPivotFacts(
        radius=value["radius"],
        preceding_high=None if value["preceding_high"] is None else _pivot(value["preceding_high"]),
        latest_high=None if value["latest_high"] is None else _pivot(value["latest_high"]),
        high_relation=None if value["high_relation"] is None else FactualPivotRelation(value["high_relation"]),
        preceding_low=None if value["preceding_low"] is None else _pivot(value["preceding_low"]),
        latest_low=None if value["latest_low"] is None else _pivot(value["latest_low"]),
        low_relation=None if value["low_relation"] is None else FactualPivotRelation(value["low_relation"]),
        condition=FactualStructureCondition(value["condition"]),
    )


def _timeframe(value: object) -> CompletedTimeframeFact:
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return CompletedTimeframeFact(
        timeframe=FactualTimeframe(value["timeframe"]),
        observation_boundary=datetime.fromisoformat(value["observation_boundary"]),
        source_timestamp=datetime.fromisoformat(value["source_timestamp"]),
        open=value["open"], high=value["high"], low=value["low"],
        close=value["close"], volume=value["volume"],
        calendar_identity=value["calendar_identity"],
        calendar_version=value["calendar_version"],
        session_identity=value["session_identity"],
        exchange_timezone=value["exchange_timezone"],
        source_interval=value["source_interval"],
        source_provider_identity=value["source_provider_identity"],
        source_market_data_boundary=datetime.fromisoformat(value["source_market_data_boundary"]),
        provenance=tuple(value["provenance"]),
        structural_measurements=tuple(_pivot_series(item) for item in value["structural_measurements"]),
        moving_averages=(
            None
            if value.get("moving_averages") is None
            else _moving_averages(value["moving_averages"])
        ),
        volume_facts=(
            None
            if value.get("volume_facts") is None
            else _volume_facts(value["volume_facts"])
        ),
        bucket_class=value["bucket_class"],
        authority=value["authority"],
    )


def _moving_averages(value: object) -> FactualMovingAverageFacts:
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return FactualMovingAverageFacts(
        value["completed_count"], value["sma20"], value["sma50"], value["sma200"],
        value["prior_sma20_5bars"], value["prior_sma50_5bars"],
        value["prior_sma200_5bars"],
    )


def _volume_facts(value: object) -> FactualVolumeFacts:
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return FactualVolumeFacts(
        value["current"], value["prior_20_mean"], value["authority"]
    )


def _pivot_series(value: object) -> FactualPivotSeries:
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return FactualPivotSeries(
        value["definition_identity"],
        value["radius"],
        tuple(_pivot(item) for item in value["swing_highs"]),
        tuple(_pivot(item) for item in value["swing_lows"]),
    )


def _pivot(value: object) -> PivotCandidate:
    if type(value) is not dict:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return PivotCandidate(
        PivotKind(value["kind"]), value["candle_index"],
        datetime.fromisoformat(value["timestamp"]), value["value"],
    )


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


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("MTF_FACT_SNAPSHOT_UNAVAILABLE") from error
    if type(value) is not dict or set(value) != {"schema", "snapshot"}:
        raise ValueError("MTF_FACT_SNAPSHOT_INVALID")
    return value


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
    "CompletedTimeframeFact", "DEFAULT_MTF_FACT_EVIDENCE_ROOT",
    "FactualMovingAverageFacts", "FactualPivotSeries", "FactualTimeframe",
    "FactualVolumeFacts", "InstrumentMtfFactSnapshot",
    "MTF_FACT_AUTHORITY", "MTF_FACT_SNAPSHOT_SCHEMA", "MtfFactEvidenceStore",
    "QUOTE_FACT_AUTHORITY", "SameRunMtfFactSnapshot",
]
