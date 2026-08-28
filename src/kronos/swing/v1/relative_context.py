"""Immutable same-run NIFTY relative context with supporting authority only."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
from threading import RLock

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.universe import (
    SWING_PHASE1_UNIVERSE,
    SwingUniverseAssetClass,
    SwingUniverseMember,
)
from kronos.swing.v1.mtf_facts import (
    CompletedTimeframeFact,
    FactualTimeframe,
    InstrumentMtfFactSnapshot,
    SameRunMtfFactSnapshot,
)
from kronos.swing.v1.policies import SWING_V1_RELATIVE_CONTEXT_POLICY_ID


RELATIVE_CONTEXT_POLICY_VERSION = "1"
RELATIVE_CONTEXT_SCHEMA = "KRONOS-SWING-V1-NIFTY-RELATIVE-CONTEXT-V1"
RELATIVE_CONTEXT_RUN_SCHEMA = "KRONOS-SWING-V1-NIFTY-RELATIVE-CONTEXT-RUN-V1"
RELATIVE_CONTEXT_AUTHORITY = (
    "SUPPORTING_CONTEXT_ONLY_NO_DISCOVERY_READINESS_TRADE_OR_EXECUTION_AUTHORITY"
)
RELATIVE_CONTEXT_BENCHMARK = "NIFTY"
DEFAULT_RELATIVE_CONTEXT_EVIDENCE_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "swing-v1"
    / "relative-context-v1"
)


class RelativeContextState(StrEnum):
    OUTPERFORMING = "OUTPERFORMING"
    UNDERPERFORMING = "UNDERPERFORMING"
    EQUAL = "EQUAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RelativeContextApplicability(StrEnum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RelativeContextReason(StrEnum):
    BENCHMARK_FACT_UNAVAILABLE = "BENCHMARK_FACT_UNAVAILABLE"
    INSTRUMENT_FACT_UNAVAILABLE = "INSTRUMENT_FACT_UNAVAILABLE"
    RUN_MISMATCH = "RUN_MISMATCH"
    TIMEFRAME_MISMATCH = "TIMEFRAME_MISMATCH"
    BOUNDARY_MISMATCH = "BOUNDARY_MISMATCH"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    SOURCE_INTEGRITY_INVALID = "SOURCE_INTEGRITY_INVALID"
    BENCHMARK_IDENTITY_INVALID = "BENCHMARK_IDENTITY_INVALID"
    NOT_APPLICABLE_ASSET_CLASS = "NOT_APPLICABLE_ASSET_CLASS"
    BENCHMARK_SELF_COMPARISON_NOT_APPLICABLE = (
        "BENCHMARK_SELF_COMPARISON_NOT_APPLICABLE"
    )


class DirectionalRelativeContext(StrEnum):
    SUPPORTIVE_CONTEXT = "SUPPORTIVE_CONTEXT"
    CONTRADICTORY_CONTEXT = "CONTRADICTORY_CONTEXT"
    NEUTRAL_CONTEXT = "NEUTRAL_CONTEXT"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class RelativeContextHorizonFact:
    timeframe: FactualTimeframe
    stock_start_boundary: datetime | None
    stock_end_boundary: datetime | None
    benchmark_start_boundary: datetime | None
    benchmark_end_boundary: datetime | None
    stock_start_price: float | None
    stock_end_price: float | None
    benchmark_start_price: float | None
    benchmark_end_price: float | None
    stock_return_pct: float | None
    benchmark_return_pct: float | None
    relative_return_pct: float | None
    relative_state: RelativeContextState
    reason_codes: tuple[RelativeContextReason, ...]
    stock_source_identity: str | None
    benchmark_source_identity: str | None
    stock_provenance: tuple[str, ...]
    benchmark_provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        numeric = (
            self.stock_start_price,
            self.stock_end_price,
            self.benchmark_start_price,
            self.benchmark_end_price,
            self.stock_return_pct,
            self.benchmark_return_pct,
            self.relative_return_pct,
        )
        available = self.relative_state in {
            RelativeContextState.OUTPERFORMING,
            RelativeContextState.UNDERPERFORMING,
            RelativeContextState.EQUAL,
        }
        boundaries = (
            self.stock_start_boundary,
            self.stock_end_boundary,
            self.benchmark_start_boundary,
            self.benchmark_end_boundary,
        )
        if (
            type(self.timeframe) is not FactualTimeframe
            or type(self.relative_state) is not RelativeContextState
            or type(self.reason_codes) is not tuple
            or any(type(item) is not RelativeContextReason for item in self.reason_codes)
            or type(self.stock_provenance) is not tuple
            or type(self.benchmark_provenance) is not tuple
            or any(
                item is not None
                and (type(item) is not float or not math.isfinite(item))
                for item in numeric
            )
            or any(item is not None and not _aware(item) for item in boundaries)
            or (
                available
                and (
                    any(item is None for item in numeric)
                    or any(item is None for item in boundaries)
                    or self.stock_start_price <= 0.0
                    or self.benchmark_start_price <= 0.0
                    or self.stock_start_boundary != self.benchmark_start_boundary
                    or self.stock_end_boundary != self.benchmark_end_boundary
                    or self.stock_source_identity is None
                    or self.benchmark_source_identity is None
                    or not self.stock_provenance
                    or not self.benchmark_provenance
                    or self.reason_codes
                    or (
                        self.relative_state is RelativeContextState.OUTPERFORMING
                        and self.relative_return_pct <= 0.0
                    )
                    or (
                        self.relative_state is RelativeContextState.UNDERPERFORMING
                        and self.relative_return_pct >= 0.0
                    )
                    or (
                        self.relative_state is RelativeContextState.EQUAL
                        and self.relative_return_pct != 0.0
                    )
                )
            )
            or (
                not available
                and (
                    not self.reason_codes
                    or any(item is not None for item in numeric)
                    or any(item is not None for item in boundaries)
                    or self.stock_source_identity is not None
                    or self.benchmark_source_identity is not None
                    or self.stock_provenance
                    or self.benchmark_provenance
                )
            )
        ):
            raise ValueError("RELATIVE_CONTEXT_HORIZON_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class RelativeContextRecord:
    run_identity: str
    canonical_instrument: str
    benchmark_identity: str
    product: SwingUniverseAssetClass
    applicability: RelativeContextApplicability
    horizons: tuple[RelativeContextHorizonFact, ...]
    created_at: datetime
    integrity_sha256: str
    policy_identity: str = SWING_V1_RELATIVE_CONTEXT_POLICY_ID
    policy_version: str = RELATIVE_CONTEXT_POLICY_VERSION
    authority: str = RELATIVE_CONTEXT_AUTHORITY
    schema: str = RELATIVE_CONTEXT_SCHEMA

    def __post_init__(self) -> None:
        states = {item.relative_state for item in self.horizons}
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument) is None
            or self.benchmark_identity != RELATIVE_CONTEXT_BENCHMARK
            or type(self.product) is not SwingUniverseAssetClass
            or type(self.applicability) is not RelativeContextApplicability
            or type(self.horizons) is not tuple
            or tuple(item.timeframe for item in self.horizons)
            != tuple(FactualTimeframe)
            or not _aware(self.created_at)
            or re.fullmatch(r"[0-9a-f]{64}", self.integrity_sha256) is None
            or self.policy_identity != SWING_V1_RELATIVE_CONTEXT_POLICY_ID
            or self.policy_version != RELATIVE_CONTEXT_POLICY_VERSION
            or self.authority != RELATIVE_CONTEXT_AUTHORITY
            or self.schema != RELATIVE_CONTEXT_SCHEMA
            or (
                self.applicability is RelativeContextApplicability.APPLICABLE
                and (
                    self.product is not SwingUniverseAssetClass.NSE_EQUITY
                    or RelativeContextState.NOT_APPLICABLE in states
                )
            )
            or (
                self.applicability is RelativeContextApplicability.NOT_APPLICABLE
                and states != {RelativeContextState.NOT_APPLICABLE}
            )
            or self.integrity_sha256 != relative_context_record_sha256(self)
        ):
            raise ValueError("RELATIVE_CONTEXT_RECORD_INVALID")

    def horizon(self, timeframe: FactualTimeframe) -> RelativeContextHorizonFact:
        return next(item for item in self.horizons if item.timeframe is timeframe)


@dataclass(frozen=True, slots=True)
class RelativeContextRun:
    run_identity: str
    created_at: datetime
    records: tuple[RelativeContextRecord, ...]
    integrity_sha256: str
    benchmark_identity: str = RELATIVE_CONTEXT_BENCHMARK
    policy_identity: str = SWING_V1_RELATIVE_CONTEXT_POLICY_ID
    policy_version: str = RELATIVE_CONTEXT_POLICY_VERSION
    authority: str = RELATIVE_CONTEXT_AUTHORITY
    schema: str = RELATIVE_CONTEXT_RUN_SCHEMA

    def __post_init__(self) -> None:
        identities = tuple(item.canonical_instrument for item in self.records)
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or not _aware(self.created_at)
            or type(self.records) is not tuple
            or len(self.records) != 98
            or len(set(identities)) != 98
            or any(
                item.run_identity != self.run_identity
                or item.created_at != self.created_at
                for item in self.records
            )
            or self.benchmark_identity != RELATIVE_CONTEXT_BENCHMARK
            or self.policy_identity != SWING_V1_RELATIVE_CONTEXT_POLICY_ID
            or self.policy_version != RELATIVE_CONTEXT_POLICY_VERSION
            or self.authority != RELATIVE_CONTEXT_AUTHORITY
            or self.schema != RELATIVE_CONTEXT_RUN_SCHEMA
            or re.fullmatch(r"[0-9a-f]{64}", self.integrity_sha256) is None
            or self.integrity_sha256 != relative_context_run_sha256(self)
        ):
            raise ValueError("RELATIVE_CONTEXT_RUN_INVALID")

    def record(self, canonical_instrument: str) -> RelativeContextRecord:
        try:
            return next(
                item for item in self.records
                if item.canonical_instrument == canonical_instrument
            )
        except StopIteration as error:
            raise ValueError("RELATIVE_CONTEXT_INSTRUMENT_UNAVAILABLE") from error


class RelativeContextEvidenceStore:
    """Immutable exact-run persistence for supporting relative context."""

    def __init__(self, root: Path = DEFAULT_RELATIVE_CONTEXT_EVIDENCE_ROOT) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("RELATIVE_CONTEXT_STORE_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain(self, run: RelativeContextRun) -> Path:
        if type(run) is not RelativeContextRun:
            raise ValueError("RELATIVE_CONTEXT_RUN_INVALID")
        path = self._path(run.run_identity)
        payload = {"schema": RELATIVE_CONTEXT_RUN_SCHEMA, "run": _json_value(asdict(run))}
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("RELATIVE_CONTEXT_RUN_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load(self, run_identity: str) -> RelativeContextRun:
        with self._lock:
            payload = _read(self._path(run_identity))
        if payload.get("schema") != RELATIVE_CONTEXT_RUN_SCHEMA:
            raise ValueError("RELATIVE_CONTEXT_RUN_INVALID")
        return _run_from_dict(payload.get("run"))

    def _path(self, run_identity: str) -> Path:
        if not is_swing_analysis_run_id(run_identity):
            raise ValueError("RELATIVE_CONTEXT_RUN_IDENTITY_INVALID")
        return self._root / "complete-runs" / f"{run_identity}.json"


def build_relative_context_run(
    snapshot: SameRunMtfFactSnapshot,
    universe: tuple[SwingUniverseMember, ...] = SWING_PHASE1_UNIVERSE,
) -> RelativeContextRun:
    """Build supporting context from one immutable same-98 MTF snapshot only."""

    if (
        type(snapshot) is not SameRunMtfFactSnapshot
        or type(universe) is not tuple
        or len(universe) != 98
        or any(type(item) is not SwingUniverseMember for item in universe)
    ):
        raise ValueError("RELATIVE_CONTEXT_BUILD_INPUT_INVALID")
    try:
        benchmark = snapshot.instrument(RELATIVE_CONTEXT_BENCHMARK)
    except ValueError:
        benchmark = None
    records = tuple(
        build_relative_context_record(
            run_identity=snapshot.run_identity,
            created_at=snapshot.observed_at,
            member=member,
            instrument=_instrument_or_none(snapshot, member.canonical_identity),
            benchmark_run_identity=snapshot.run_identity,
            benchmark=benchmark,
        )
        for member in universe
    )
    digest = _run_values_sha256(
        snapshot.run_identity, snapshot.observed_at, records,
        RELATIVE_CONTEXT_BENCHMARK, SWING_V1_RELATIVE_CONTEXT_POLICY_ID,
        RELATIVE_CONTEXT_POLICY_VERSION, RELATIVE_CONTEXT_AUTHORITY,
        RELATIVE_CONTEXT_RUN_SCHEMA,
    )
    return RelativeContextRun(
        snapshot.run_identity, snapshot.observed_at, records, digest,
    )


def build_relative_context_record(
    *,
    run_identity: str,
    created_at: datetime,
    member: SwingUniverseMember,
    instrument: InstrumentMtfFactSnapshot | None,
    benchmark_run_identity: str,
    benchmark: InstrumentMtfFactSnapshot | None,
) -> RelativeContextRecord:
    if (
        not is_swing_analysis_run_id(run_identity)
        or not _aware(created_at)
        or type(member) is not SwingUniverseMember
        or (instrument is not None and type(instrument) is not InstrumentMtfFactSnapshot)
        or not is_swing_analysis_run_id(benchmark_run_identity)
        or (benchmark is not None and type(benchmark) is not InstrumentMtfFactSnapshot)
    ):
        raise ValueError("RELATIVE_CONTEXT_BUILD_INPUT_INVALID")
    not_applicable = member.asset_class is not SwingUniverseAssetClass.NSE_EQUITY
    if not_applicable:
        reason = (
            RelativeContextReason.BENCHMARK_SELF_COMPARISON_NOT_APPLICABLE
            if member.canonical_identity == RELATIVE_CONTEXT_BENCHMARK
            else RelativeContextReason.NOT_APPLICABLE_ASSET_CLASS
        )
        horizons = tuple(
            _unavailable_horizon(
                timeframe, RelativeContextState.NOT_APPLICABLE, reason
            )
            for timeframe in FactualTimeframe
        )
        applicability = RelativeContextApplicability.NOT_APPLICABLE
    else:
        applicability = RelativeContextApplicability.APPLICABLE
        if benchmark_run_identity != run_identity:
            horizons = tuple(
                _unavailable_horizon(
                    timeframe, RelativeContextState.UNAVAILABLE,
                    RelativeContextReason.RUN_MISMATCH,
                )
                for timeframe in FactualTimeframe
            )
        elif benchmark is None:
            horizons = tuple(
                _unavailable_horizon(
                    timeframe, RelativeContextState.UNAVAILABLE,
                    RelativeContextReason.BENCHMARK_FACT_UNAVAILABLE,
                )
                for timeframe in FactualTimeframe
            )
        elif benchmark.canonical_instrument != RELATIVE_CONTEXT_BENCHMARK:
            horizons = tuple(
                _unavailable_horizon(
                    timeframe, RelativeContextState.UNAVAILABLE,
                    RelativeContextReason.BENCHMARK_IDENTITY_INVALID,
                )
                for timeframe in FactualTimeframe
            )
        elif instrument is None:
            horizons = tuple(
                _unavailable_horizon(
                    timeframe, RelativeContextState.UNAVAILABLE,
                    RelativeContextReason.INSTRUMENT_FACT_UNAVAILABLE,
                )
                for timeframe in FactualTimeframe
            )
        elif instrument.canonical_instrument != member.canonical_identity:
            horizons = tuple(
                _unavailable_horizon(
                    timeframe, RelativeContextState.UNAVAILABLE,
                    RelativeContextReason.SOURCE_INTEGRITY_INVALID,
                )
                for timeframe in FactualTimeframe
            )
        else:
            horizons = tuple(
                _compare_horizon(
                    instrument.fact(timeframe), benchmark.fact(timeframe)
                )
                for timeframe in FactualTimeframe
            )
    digest = _record_values_sha256(
        run_identity, member.canonical_identity, RELATIVE_CONTEXT_BENCHMARK,
        member.asset_class, applicability, horizons, created_at,
        SWING_V1_RELATIVE_CONTEXT_POLICY_ID, RELATIVE_CONTEXT_POLICY_VERSION,
        RELATIVE_CONTEXT_AUTHORITY, RELATIVE_CONTEXT_SCHEMA,
    )
    return RelativeContextRecord(
        run_identity, member.canonical_identity, RELATIVE_CONTEXT_BENCHMARK,
        member.asset_class, applicability, horizons, created_at, digest,
    )


def directional_relative_context(
    state: RelativeContextState, direction: str
) -> DirectionalRelativeContext:
    if type(state) is not RelativeContextState or direction not in {"LONG", "SHORT"}:
        raise ValueError("RELATIVE_CONTEXT_DIRECTION_INVALID")
    if state is RelativeContextState.UNAVAILABLE:
        return DirectionalRelativeContext.UNAVAILABLE
    if state is RelativeContextState.NOT_APPLICABLE:
        return DirectionalRelativeContext.NOT_APPLICABLE
    if state is RelativeContextState.EQUAL:
        return DirectionalRelativeContext.NEUTRAL_CONTEXT
    supportive = (
        state is RelativeContextState.OUTPERFORMING and direction == "LONG"
    ) or (
        state is RelativeContextState.UNDERPERFORMING and direction == "SHORT"
    )
    return (
        DirectionalRelativeContext.SUPPORTIVE_CONTEXT
        if supportive
        else DirectionalRelativeContext.CONTRADICTORY_CONTEXT
    )


def _compare_horizon(
    stock: CompletedTimeframeFact,
    benchmark: CompletedTimeframeFact,
) -> RelativeContextHorizonFact:
    if stock.timeframe is not benchmark.timeframe:
        return _unavailable_horizon(
            stock.timeframe, RelativeContextState.UNAVAILABLE,
            RelativeContextReason.TIMEFRAME_MISMATCH,
        )
    if (
        stock.source_timestamp != benchmark.source_timestamp
        or stock.observation_boundary != benchmark.observation_boundary
        or stock.calendar_identity != benchmark.calendar_identity
        or stock.calendar_version != benchmark.calendar_version
        or stock.session_identity != benchmark.session_identity
        or stock.source_interval != benchmark.source_interval
    ):
        return _unavailable_horizon(
            stock.timeframe, RelativeContextState.UNAVAILABLE,
            RelativeContextReason.BOUNDARY_MISMATCH,
        )
    if stock.open <= 0.0 or benchmark.open <= 0.0:
        return _unavailable_horizon(
            stock.timeframe, RelativeContextState.UNAVAILABLE,
            RelativeContextReason.INSUFFICIENT_HISTORY,
        )
    stock_return = ((stock.close / stock.open) - 1.0) * 100.0
    benchmark_return = ((benchmark.close / benchmark.open) - 1.0) * 100.0
    relative_return = stock_return - benchmark_return
    state = (
        RelativeContextState.OUTPERFORMING
        if relative_return > 0.0
        else RelativeContextState.UNDERPERFORMING
        if relative_return < 0.0
        else RelativeContextState.EQUAL
    )
    return RelativeContextHorizonFact(
        stock.timeframe,
        stock.source_timestamp,
        stock.observation_boundary,
        benchmark.source_timestamp,
        benchmark.observation_boundary,
        stock.open,
        stock.close,
        benchmark.open,
        benchmark.close,
        stock_return,
        benchmark_return,
        relative_return,
        state,
        (),
        _source_identity(stock),
        _source_identity(benchmark),
        stock.provenance,
        benchmark.provenance,
    )


def _unavailable_horizon(
    timeframe: FactualTimeframe,
    state: RelativeContextState,
    reason: RelativeContextReason,
) -> RelativeContextHorizonFact:
    return RelativeContextHorizonFact(
        timeframe, None, None, None, None,
        None, None, None, None, None, None, None,
        state, (reason,), None, None, (), (),
    )


def _source_identity(fact: CompletedTimeframeFact) -> str:
    payload = {
        "timeframe": fact.timeframe.value,
        "start": fact.source_timestamp.isoformat(),
        "end": fact.observation_boundary.isoformat(),
        "ohlcv": [fact.open, fact.high, fact.low, fact.close, fact.volume],
        "calendar": [fact.calendar_identity, fact.calendar_version],
        "session": fact.session_identity,
        "source_interval": fact.source_interval,
        "source_provider_identity": fact.source_provider_identity,
        "source_market_data_boundary": fact.source_market_data_boundary.isoformat(),
        "provenance": list(fact.provenance),
    }
    return sha256(_canonical_json(payload)).hexdigest()


def relative_context_record_sha256(record: RelativeContextRecord) -> str:
    return _record_values_sha256(
        record.run_identity, record.canonical_instrument,
        record.benchmark_identity, record.product, record.applicability,
        record.horizons, record.created_at, record.policy_identity,
        record.policy_version, record.authority, record.schema,
    )


def relative_context_run_sha256(run: RelativeContextRun) -> str:
    return _run_values_sha256(
        run.run_identity, run.created_at, run.records, run.benchmark_identity,
        run.policy_identity, run.policy_version, run.authority, run.schema,
    )


def _record_values_sha256(
    run_identity: str,
    canonical_instrument: str,
    benchmark_identity: str,
    product: SwingUniverseAssetClass,
    applicability: RelativeContextApplicability,
    horizons: tuple[RelativeContextHorizonFact, ...],
    created_at: datetime,
    policy_identity: str,
    policy_version: str,
    authority: str,
    schema: str,
) -> str:
    return sha256(_canonical_json({
        "run_identity": run_identity,
        "canonical_instrument": canonical_instrument,
        "benchmark_identity": benchmark_identity,
        "product": product,
        "applicability": applicability,
        "horizons": [_json_value(asdict(item)) for item in horizons],
        "created_at": created_at,
        "integrity_sha256": "",
        "policy_identity": policy_identity,
        "policy_version": policy_version,
        "authority": authority,
        "schema": schema,
    })).hexdigest()


def _run_values_sha256(
    run_identity: str,
    created_at: datetime,
    records: tuple[RelativeContextRecord, ...],
    benchmark_identity: str,
    policy_identity: str,
    policy_version: str,
    authority: str,
    schema: str,
) -> str:
    return sha256(_canonical_json({
        "run_identity": run_identity,
        "created_at": created_at,
        "records": [_json_value(asdict(item)) for item in records],
        "integrity_sha256": "",
        "benchmark_identity": benchmark_identity,
        "policy_identity": policy_identity,
        "policy_version": policy_version,
        "authority": authority,
        "schema": schema,
    })).hexdigest()


def _instrument_or_none(
    snapshot: SameRunMtfFactSnapshot, canonical_identity: str
) -> InstrumentMtfFactSnapshot | None:
    try:
        return snapshot.instrument(canonical_identity)
    except ValueError:
        return None


def _run_from_dict(value: object) -> RelativeContextRun:
    if type(value) is not dict:
        raise ValueError("RELATIVE_CONTEXT_RUN_INVALID")
    try:
        return RelativeContextRun(
            value["run_identity"],
            datetime.fromisoformat(value["created_at"]),
            tuple(_record_from_dict(item) for item in value["records"]),
            value["integrity_sha256"],
            value["benchmark_identity"],
            value["policy_identity"],
            value["policy_version"],
            value["authority"],
            value["schema"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("RELATIVE_CONTEXT_RUN_INVALID") from error


def _record_from_dict(value: object) -> RelativeContextRecord:
    if type(value) is not dict:
        raise ValueError("RELATIVE_CONTEXT_RECORD_INVALID")
    return RelativeContextRecord(
        value["run_identity"], value["canonical_instrument"],
        value["benchmark_identity"], SwingUniverseAssetClass(value["product"]),
        RelativeContextApplicability(value["applicability"]),
        tuple(_horizon_from_dict(item) for item in value["horizons"]),
        datetime.fromisoformat(value["created_at"]), value["integrity_sha256"],
        value["policy_identity"], value["policy_version"],
        value["authority"], value["schema"],
    )


def _horizon_from_dict(value: object) -> RelativeContextHorizonFact:
    if type(value) is not dict:
        raise ValueError("RELATIVE_CONTEXT_HORIZON_FACT_INVALID")
    boundary = lambda key: (
        None if value[key] is None else datetime.fromisoformat(value[key])
    )
    return RelativeContextHorizonFact(
        FactualTimeframe(value["timeframe"]),
        boundary("stock_start_boundary"), boundary("stock_end_boundary"),
        boundary("benchmark_start_boundary"), boundary("benchmark_end_boundary"),
        value["stock_start_price"], value["stock_end_price"],
        value["benchmark_start_price"], value["benchmark_end_price"],
        value["stock_return_pct"], value["benchmark_return_pct"],
        value["relative_return_pct"], RelativeContextState(value["relative_state"]),
        tuple(RelativeContextReason(item) for item in value["reason_codes"]),
        value["stock_source_identity"], value["benchmark_source_identity"],
        tuple(value["stock_provenance"]), tuple(value["benchmark_provenance"]),
    )


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _json_value(value), sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("RELATIVE_CONTEXT_EVIDENCE_INVALID") from error
    if type(value) is not dict:
        raise ValueError("RELATIVE_CONTEXT_EVIDENCE_INVALID")
    return value


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "DEFAULT_RELATIVE_CONTEXT_EVIDENCE_ROOT",
    "DirectionalRelativeContext",
    "RELATIVE_CONTEXT_AUTHORITY",
    "RELATIVE_CONTEXT_BENCHMARK",
    "RELATIVE_CONTEXT_POLICY_VERSION",
    "RELATIVE_CONTEXT_RUN_SCHEMA",
    "RELATIVE_CONTEXT_SCHEMA",
    "RelativeContextApplicability",
    "RelativeContextEvidenceStore",
    "RelativeContextHorizonFact",
    "RelativeContextReason",
    "RelativeContextRecord",
    "RelativeContextRun",
    "RelativeContextState",
    "build_relative_context_record",
    "build_relative_context_run",
    "directional_relative_context",
    "relative_context_record_sha256",
    "relative_context_run_sha256",
]
