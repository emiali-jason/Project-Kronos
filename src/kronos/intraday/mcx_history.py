"""Production MCX actual-contract candle retention and analytical replay.

Only completed candles already acquired by a governed Intraday operation enter
this contract. Retention never performs Provider reads and the reconstructed
continuous view is analytical, non-back-adjusted, and non-executable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.instrument.active_derivative import ActiveDerivativeBindingArtifact
from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe
from kronos.market.schedule import MarketDaySchedule
from kronos.provider.contracts.market_data import HistoricalCandle


MCX_HISTORY_CANDLE_IDENTITY = (
    "KRONOS-INTRADAY-MCX-HISTORICAL-CONTRACT-CANDLE-V1"
)
MCX_HISTORY_CANDLE_VERSION = "1.0.0"
MCX_CONTINUOUS_VIEW_IDENTITY = (
    "KRONOS-INTRADAY-MCX-CONTINUOUS-ANALYTICAL-VIEW-V1"
)
MCX_CONTINUOUS_VIEW_VERSION = "1.0.0"
MCX_HISTORY_AUTHORITY = "FACTUAL_HISTORICAL_ANALYTICAL_EVIDENCE_ONLY"
MCX_CONTINUOUS_CONSTRUCTION = "KRONOS_CONSTRUCTED_EXACT_CONTRACT_SEGMENTS"


class McxHistoryError(ValueError):
    """Sanitized retention, lineage, or integrity failure."""


@dataclass(frozen=True, slots=True)
class RetainedMcxContractCandle:
    candle_identity: str
    canonical_subject_identity: str
    canonical_contract_identity: str
    provider_record_identity: str
    historical_binding_identity: str
    domain008_session_identity: str
    calendar_identity: str
    calendar_version: str
    timeframe: IntradayTimeframe
    source_timestamp: datetime
    candle_start: datetime
    candle_end: datetime
    completion_boundary: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    observation_boundary: datetime
    source_operation_identity: str
    provider_source_identity: str
    provenance: tuple[str, ...]
    authority: str
    integrity_identity: str
    contract_identity: str = MCX_HISTORY_CANDLE_IDENTITY
    contract_version: str = MCX_HISTORY_CANDLE_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("candle_identity")
        values.pop("integrity_identity")
        prices = (self.open, self.high, self.low, self.close)
        if (
            not self.candle_identity.startswith("INTRADAY-MCX-CONTRACT-CANDLE-")
            or not _texts((
                self.canonical_subject_identity,
                self.canonical_contract_identity,
                self.provider_record_identity,
                self.historical_binding_identity,
                self.domain008_session_identity,
                self.calendar_identity,
                self.calendar_version,
                self.source_operation_identity,
                self.provider_source_identity,
                self.authority,
            ))
            or not self.canonical_subject_identity.startswith("MCX-SUBJECT-")
            or not self.canonical_contract_identity.startswith("MCX-FUT-")
            or not self.provider_record_identity.startswith("PROVIDER-INSTRUMENT-RECORD-")
            or type(self.timeframe) is not IntradayTimeframe
            or not all(_aware(item) for item in (
                self.source_timestamp,
                self.candle_start,
                self.candle_end,
                self.completion_boundary,
                self.observation_boundary,
            ))
            or self.candle_start >= self.candle_end
            or self.completion_boundary != self.candle_end
            or self.candle_end > self.observation_boundary
            or any(type(item) is not Decimal or not item.is_finite() or item < 0 for item in prices)
            or self.high < max(self.open, self.low, self.close)
            or self.low > min(self.open, self.high, self.close)
            or type(self.volume) is not int
            or self.volume < 0
            or not _texts(self.provenance)
            or self.authority != MCX_HISTORY_AUTHORITY
            or self.contract_identity != MCX_HISTORY_CANDLE_IDENTITY
            or self.contract_version != MCX_HISTORY_CANDLE_VERSION
            or self.candle_identity != _identity("INTRADAY-MCX-CONTRACT-CANDLE-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-CONTRACT-CANDLE-", values)
        ):
            raise McxHistoryError("MCX_RETAINED_CANDLE_INVALID")


@dataclass(frozen=True, slots=True)
class McxContractRollBoundary:
    boundary_identity: str
    canonical_subject_identity: str
    old_contract_identity: str
    new_contract_identity: str
    old_contract_last_candle_end: datetime
    new_contract_first_candle_start: datetime
    price_adjustment: str
    market_gap_authority: str
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("boundary_identity")
        values.pop("integrity_identity")
        if (
            not self.boundary_identity.startswith("INTRADAY-MCX-CONTRACT-ROLL-")
            or not _texts((self.canonical_subject_identity, self.old_contract_identity, self.new_contract_identity))
            or self.old_contract_identity == self.new_contract_identity
            or not _aware(self.old_contract_last_candle_end)
            or not _aware(self.new_contract_first_candle_start)
            or self.price_adjustment != "NONE_NON_BACK_ADJUSTED"
            or self.market_gap_authority != "NOT_ESTABLISHED_BY_ROLL"
            or self.boundary_identity != _identity("INTRADAY-MCX-CONTRACT-ROLL-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-CONTRACT-ROLL-", values)
        ):
            raise McxHistoryError("MCX_CONTRACT_ROLL_INVALID")


@dataclass(frozen=True, slots=True)
class McxContinuousAnalyticalView:
    view_identity: str
    canonical_subject_identity: str
    contract_identities: tuple[str, ...]
    candles: tuple[RetainedMcxContractCandle, ...]
    roll_boundaries: tuple[McxContractRollBoundary, ...]
    missing_segment_identities: tuple[str, ...]
    construction_method: str
    back_adjustment: str
    executable: bool
    provider_request_count: int
    integrity_identity: str
    contract_identity: str = MCX_CONTINUOUS_VIEW_IDENTITY
    contract_version: str = MCX_CONTINUOUS_VIEW_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("view_identity")
        values.pop("integrity_identity")
        if (
            not self.view_identity.startswith("INTRADAY-MCX-CONTINUOUS-VIEW-")
            or not self.canonical_subject_identity.startswith("MCX-SUBJECT-")
            or not _texts(self.contract_identities)
            or not self.candles
            or any(type(item) is not RetainedMcxContractCandle for item in self.candles)
            or any(item.canonical_subject_identity != self.canonical_subject_identity for item in self.candles)
            or any(item.canonical_contract_identity not in self.contract_identities for item in self.candles)
            or any(type(item) is not McxContractRollBoundary for item in self.roll_boundaries)
            or self.construction_method != MCX_CONTINUOUS_CONSTRUCTION
            or self.back_adjustment != "NONE"
            or self.executable is not False
            or self.provider_request_count != 0
            or self.contract_identity != MCX_CONTINUOUS_VIEW_IDENTITY
            or self.contract_version != MCX_CONTINUOUS_VIEW_VERSION
            or self.view_identity != _identity("INTRADAY-MCX-CONTINUOUS-VIEW-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-CONTINUOUS-VIEW-", values)
        ):
            raise McxHistoryError("MCX_CONTINUOUS_VIEW_INVALID")


def create_retained_mcx_candles(
    *,
    active_binding: ActiveDerivativeBindingArtifact,
    timeframe: IntradayTimeframe,
    schedule: MarketDaySchedule,
    candles: Sequence[HistoricalCandle],
    observation_boundary: datetime,
    source_operation_identity: str,
) -> tuple[RetainedMcxContractCandle, ...]:
    """Adapt already-acquired completed candles; never call a Provider."""

    if (
        type(active_binding) is not ActiveDerivativeBindingArtifact
        or type(timeframe) is not IntradayTimeframe
        or type(schedule) is not MarketDaySchedule
        or not _aware(observation_boundary)
        or not _text(source_operation_identity)
        or any(type(item) is not HistoricalCandle for item in candles)
    ):
        raise McxHistoryError("MCX_RETENTION_INPUT_INVALID")
    boundaries = expected_candle_boundaries(schedule, timeframe)
    by_start = {item.start: item for item in boundaries}
    results: list[RetainedMcxContractCandle] = []
    for candle in candles:
        if timeframe is IntradayTimeframe.DAILY:
            start = schedule.windows[0].opens_at
            end = schedule.windows[-1].closes_at
        else:
            boundary = by_start.get(candle.timestamp)
            if boundary is None:
                raise McxHistoryError("MCX_RETENTION_CANDLE_MISALIGNED")
            start, end = boundary.start, boundary.end
        if end > observation_boundary.astimezone(end.tzinfo):
            raise McxHistoryError("MCX_RETENTION_FORMING_CANDLE_REJECTED")
        values = {
            "canonical_subject_identity": active_binding.canonical_subject_id,
            "canonical_contract_identity": active_binding.active_binding.derivative_contract_id,
            "provider_record_identity": active_binding.provider_record_identity,
            "historical_binding_identity": active_binding.binding_identity,
            "domain008_session_identity": schedule.session_id,
            "calendar_identity": schedule.source_identity,
            "calendar_version": schedule.source_version,
            "timeframe": timeframe,
            "source_timestamp": candle.timestamp,
            "candle_start": start,
            "candle_end": end,
            "completion_boundary": end,
            "open": Decimal(str(candle.open)),
            "high": Decimal(str(candle.high)),
            "low": Decimal(str(candle.low)),
            "close": Decimal(str(candle.close)),
            "volume": candle.volume,
            "observation_boundary": observation_boundary,
            "source_operation_identity": source_operation_identity,
            "provider_source_identity": "DOMAIN-006:KITE:HISTORICAL",
            "provenance": (
                active_binding.integrity_identity,
                active_binding.provider_snapshot_identity,
                "REUSED_GOVERNED_DISCOVERY_ACQUISITION",
                "SENSITIVE_PROVIDER_LOCATOR_EXCLUDED",
            ),
            "authority": MCX_HISTORY_AUTHORITY,
            "contract_identity": MCX_HISTORY_CANDLE_IDENTITY,
            "contract_version": MCX_HISTORY_CANDLE_VERSION,
        }
        results.append(RetainedMcxContractCandle(
            candle_identity=_identity("INTRADAY-MCX-CONTRACT-CANDLE-", values),
            integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-CONTRACT-CANDLE-", values),
            **values,
        ))
    return tuple(results)


def build_continuous_analytical_view(
    *,
    canonical_subject_identity: str,
    contract_identities: Sequence[str],
    candles: Sequence[RetainedMcxContractCandle],
) -> McxContinuousAnalyticalView:
    contracts = tuple(contract_identities)
    supplied = tuple(candles)
    if (
        not canonical_subject_identity.startswith("MCX-SUBJECT-")
        or not _texts(contracts)
        or len(set(contracts)) != len(contracts)
        or not supplied
        or any(type(item) is not RetainedMcxContractCandle for item in supplied)
    ):
        raise McxHistoryError("MCX_CONTINUOUS_VIEW_INPUT_INVALID")
    ordered = tuple(sorted(supplied, key=lambda item: (
        item.timeframe.value, item.candle_start, contracts.index(item.canonical_contract_identity)
    )))
    rolls: list[McxContractRollBoundary] = []
    for old, new in zip(contracts, contracts[1:]):
        old_candles = tuple(item for item in ordered if item.canonical_contract_identity == old)
        new_candles = tuple(item for item in ordered if item.canonical_contract_identity == new)
        if not old_candles or not new_candles:
            continue
        roll_values = {
            "canonical_subject_identity": canonical_subject_identity,
            "old_contract_identity": old,
            "new_contract_identity": new,
            "old_contract_last_candle_end": max(item.candle_end for item in old_candles),
            "new_contract_first_candle_start": min(item.candle_start for item in new_candles),
            "price_adjustment": "NONE_NON_BACK_ADJUSTED",
            "market_gap_authority": "NOT_ESTABLISHED_BY_ROLL",
        }
        rolls.append(McxContractRollBoundary(
            boundary_identity=_identity("INTRADAY-MCX-CONTRACT-ROLL-", roll_values),
            integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-CONTRACT-ROLL-", roll_values),
            **roll_values,
        ))
    missing = tuple(
        f"MISSING-CONTRACT-SEGMENT:{item}"
        for item in contracts
        if not any(value.canonical_contract_identity == item for value in ordered)
    )
    values = {
        "canonical_subject_identity": canonical_subject_identity,
        "contract_identities": contracts,
        "candles": ordered,
        "roll_boundaries": tuple(rolls),
        "missing_segment_identities": missing,
        "construction_method": MCX_CONTINUOUS_CONSTRUCTION,
        "back_adjustment": "NONE",
        "executable": False,
        "provider_request_count": 0,
        "contract_identity": MCX_CONTINUOUS_VIEW_IDENTITY,
        "contract_version": MCX_CONTINUOUS_VIEW_VERSION,
    }
    return McxContinuousAnalyticalView(
        view_identity=_identity("INTRADAY-MCX-CONTINUOUS-VIEW-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-CONTINUOUS-VIEW-", values),
        **values,
    )


def retained_mcx_candle_bytes(value: RetainedMcxContractCandle) -> bytes:
    if type(value) is not RetainedMcxContractCandle:
        raise McxHistoryError("MCX_RETAINED_CANDLE_INVALID")
    return _encode(value) + b"\n"


def parse_retained_mcx_candle(encoded: bytes) -> RetainedMcxContractCandle:
    try:
        values = dict(json.loads(encoded))
        values["timeframe"] = IntradayTimeframe(values["timeframe"])
        for name in (
            "source_timestamp", "candle_start", "candle_end",
            "completion_boundary", "observation_boundary",
        ):
            values[name] = datetime.fromisoformat(values[name])
        for name in ("open", "high", "low", "close"):
            values[name] = Decimal(values[name])
        values["provenance"] = tuple(values["provenance"])
        value = RetainedMcxContractCandle(**values)
    except McxHistoryError:
        raise
    except Exception as error:
        raise McxHistoryError("MCX_RETAINED_CANDLE_CORRUPT") from error
    if retained_mcx_candle_bytes(value) != encoded:
        raise McxHistoryError("MCX_RETAINED_CANDLE_CORRUPT")
    return value


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":")).encode()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(item) for item in values)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "MCX_CONTINUOUS_CONSTRUCTION",
    "MCX_CONTINUOUS_VIEW_IDENTITY",
    "MCX_CONTINUOUS_VIEW_VERSION",
    "MCX_HISTORY_CANDLE_IDENTITY",
    "MCX_HISTORY_CANDLE_VERSION",
    "McxContinuousAnalyticalView",
    "McxContractRollBoundary",
    "McxHistoryError",
    "RetainedMcxContractCandle",
    "build_continuous_analytical_view",
    "create_retained_mcx_candles",
    "parse_retained_mcx_candle",
    "retained_mcx_candle_bytes",
]
