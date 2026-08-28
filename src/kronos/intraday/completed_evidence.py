"""Phase-aware completed-evidence selection for Intraday Probables V2.

DOMAIN-008 supplies the schedules. This module only selects immutable,
already-completed Intraday evidence for one subject and analysis boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload
from kronos.market.schedule import MarketDaySchedule, TradingDayStatus


COMPLETED_EVIDENCE_SELECTION_IDENTITY = (
    "KRONOS-INTRADAY-PHASE-AWARE-COMPLETED-EVIDENCE-SELECTION-V1"
)
COMPLETED_EVIDENCE_SELECTION_VERSION = "1.0.0"
COMPLETED_EVIDENCE_SELECTION_POLICY = (
    "KRONOS-INTRADAY-PHASE-AWARE-COMPLETED-EVIDENCE-SELECTION-POLICY-V1"
)
COMPLETED_EVIDENCE_SELECTION_POLICY_VERSION = "1.0.0"


class CompletedEvidenceError(ValueError):
    """Sanitized invalid, incomplete, or conflicting completed evidence."""


class IntradayAnalysisPhase(StrEnum):
    OPENING = "OPENING"
    STRUCTURE = "STRUCTURE"
    FIRST_CURRENT_SESSION_1H = "FIRST_CURRENT_SESSION_1H"
    CURRENT_SESSION_ESTABLISHED = "CURRENT_SESSION_ESTABLISHED"


class EvidenceSessionRole(StrEnum):
    PREVIOUS_SESSION_DAILY = "PREVIOUS_SESSION_DAILY"
    PRIOR_SESSION_1H_CONTEXT = "PRIOR_SESSION_1H_CONTEXT"
    CURRENT_SESSION_1H_PRIMARY = "CURRENT_SESSION_1H_PRIMARY"
    CURRENT_SESSION_15M = "CURRENT_SESSION_15M"
    CURRENT_SESSION_5M = "CURRENT_SESSION_5M"


@dataclass(frozen=True, slots=True)
class SelectedCompletedCandle:
    candle: GovernedHistoricalCandlePayload
    source_timestamp: datetime
    completion_boundary: datetime
    original_market_session_identity: str
    session_role: EvidenceSessionRole

    def __post_init__(self) -> None:
        if (
            type(self.candle) is not GovernedHistoricalCandlePayload
            or self.candle.completion_state != "COMPLETE"
            or self.source_timestamp != self.candle.candle_start
            or self.completion_boundary != self.candle.candle_end
            or self.original_market_session_identity
            != self.candle.market_session_identity
            or type(self.session_role) is not EvidenceSessionRole
        ):
            raise CompletedEvidenceError("COMPLETED_EVIDENCE_CANDLE_INVALID")


@dataclass(frozen=True, slots=True)
class PhaseAwareCompletedEvidenceSelection:
    selection_identity: str
    canonical_subject_identity: str
    analysis_boundary: datetime
    phase: IntradayAnalysisPhase
    calendar_identity: str
    calendar_version: str
    market_identity: str
    current_market_session_identity: str
    previous_market_session_identity: str
    selected_candles: tuple[SelectedCompletedCandle, ...]
    source_operation_identities: tuple[str, ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    selection_policy_identity: str = COMPLETED_EVIDENCE_SELECTION_POLICY
    selection_policy_version: str = COMPLETED_EVIDENCE_SELECTION_POLICY_VERSION
    schema_identity: str = COMPLETED_EVIDENCE_SELECTION_IDENTITY
    schema_version: str = COMPLETED_EVIDENCE_SELECTION_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("selection_identity")
        values.pop("integrity_identity")
        candles = tuple(item.candle for item in self.selected_candles)
        if (
            not self.selection_identity.startswith("INTRADAY-COMPLETED-EVIDENCE-")
            or not _texts((
                self.canonical_subject_identity,
                self.calendar_identity,
                self.calendar_version,
                self.market_identity,
                self.current_market_session_identity,
                self.previous_market_session_identity,
            ))
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or not self.selected_candles
            or any(type(item) is not SelectedCompletedCandle for item in self.selected_candles)
            or len({item.candle.candle_identity for item in self.selected_candles})
            != len(self.selected_candles)
            or any(item.candle.canonical_subject_identity != self.canonical_subject_identity for item in self.selected_candles)
            or any(item.candle.candle_end > self.analysis_boundary for item in self.selected_candles)
            or tuple(sorted(self.selected_candles, key=_selected_key)) != self.selected_candles
            or not _texts(self.source_operation_identities)
            or tuple(sorted(set(self.source_operation_identities)))
            != self.source_operation_identities
            or set(self.source_operation_identities)
            != {item.source_operation_identity for item in candles}
            or not _texts(self.provenance)
            or self.selection_policy_identity != COMPLETED_EVIDENCE_SELECTION_POLICY
            or self.selection_policy_version != COMPLETED_EVIDENCE_SELECTION_POLICY_VERSION
            or self.schema_identity != COMPLETED_EVIDENCE_SELECTION_IDENTITY
            or self.schema_version != COMPLETED_EVIDENCE_SELECTION_VERSION
            or self.selection_identity
            != _identity("INTRADAY-COMPLETED-EVIDENCE-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-COMPLETED-EVIDENCE-", values)
        ):
            raise CompletedEvidenceError("COMPLETED_EVIDENCE_SELECTION_INVALID")
        _require_phase_shape(self)

    def candles(
        self,
        timeframe: IntradayTimeframe,
        role: EvidenceSessionRole | None = None,
    ) -> tuple[GovernedHistoricalCandlePayload, ...]:
        return tuple(
            item.candle
            for item in self.selected_candles
            if item.candle.timeframe is timeframe
            and (role is None or item.session_role is role)
        )


def select_intraday_analysis_phase(
    *,
    current_completed_15m_count: int,
    current_completed_1h_count: int,
) -> IntradayAnalysisPhase | None:
    """Select the exact frozen phase from completed counts, never clock labels."""

    if (
        type(current_completed_15m_count) is not int
        or current_completed_15m_count < 0
        or type(current_completed_1h_count) is not int
        or current_completed_1h_count < 0
    ):
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_COUNTS_INVALID")
    if current_completed_1h_count >= 2:
        return IntradayAnalysisPhase.CURRENT_SESSION_ESTABLISHED
    if current_completed_1h_count == 1:
        return IntradayAnalysisPhase.FIRST_CURRENT_SESSION_1H
    if current_completed_15m_count >= 2:
        return IntradayAnalysisPhase.STRUCTURE
    if current_completed_15m_count == 1:
        return IntradayAnalysisPhase.OPENING
    return None


def phase_aware_historical_window(
    *,
    current_schedule: MarketDaySchedule,
    previous_schedule: MarketDaySchedule,
    observation_boundary: datetime,
) -> tuple[datetime, datetime]:
    """Return the minimum governed window spanning prior context and now."""

    _require_schedule_pair(current_schedule, previous_schedule, observation_boundary)
    end = min(
        observation_boundary.astimezone(current_schedule.windows[-1].closes_at.tzinfo),
        current_schedule.windows[-1].closes_at,
    )
    start = previous_schedule.windows[0].opens_at
    if start >= end:
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_WINDOW_INVALID")
    return start, end


def build_completed_evidence_selection(
    *,
    canonical_subject_identity: str,
    analysis_boundary: datetime,
    current_schedule: MarketDaySchedule,
    previous_schedule: MarketDaySchedule,
    previous_daily: Sequence[GovernedHistoricalCandlePayload],
    previous_one_hour: Sequence[GovernedHistoricalCandlePayload],
    current_one_hour: Sequence[GovernedHistoricalCandlePayload],
    current_fifteen_minute: Sequence[GovernedHistoricalCandlePayload],
    current_five_minute: Sequence[GovernedHistoricalCandlePayload],
    provenance: tuple[str, ...],
) -> PhaseAwareCompletedEvidenceSelection:
    """Select one immutable phase-specific evidence set or fail closed."""

    if not _text(canonical_subject_identity) or not _texts(provenance):
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_INPUT_INVALID")
    _require_schedule_pair(current_schedule, previous_schedule, analysis_boundary)
    groups = {
        "previous_daily": tuple(previous_daily),
        "previous_one_hour": tuple(previous_one_hour),
        "current_one_hour": tuple(current_one_hour),
        "current_fifteen_minute": tuple(current_fifteen_minute),
        "current_five_minute": tuple(current_five_minute),
    }
    if any(
        type(item) is not GovernedHistoricalCandlePayload
        for values in groups.values()
        for item in values
    ):
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_INPUT_INVALID")
    for values in groups.values():
        _require_canonical_order(values)
        if any(
            item.canonical_subject_identity != canonical_subject_identity
            or item.candle_end > analysis_boundary
            for item in values
        ):
            raise CompletedEvidenceError("COMPLETED_EVIDENCE_SUBJECT_OR_BOUNDARY_MISMATCH")
    if len(groups["previous_daily"]) != 1:
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_PREVIOUS_DAILY_UNAVAILABLE")

    _require_schedule_candles(
        groups["previous_daily"], previous_schedule, IntradayTimeframe.DAILY,
        allow_daily=True,
    )
    _require_schedule_candles(
        groups["previous_one_hour"], previous_schedule, IntradayTimeframe.ONE_HOUR,
    )
    _require_schedule_candles(
        groups["current_one_hour"], current_schedule, IntradayTimeframe.ONE_HOUR,
    )
    _require_schedule_candles(
        groups["current_fifteen_minute"], current_schedule,
        IntradayTimeframe.FIFTEEN_MINUTES,
    )
    _require_schedule_candles(
        groups["current_five_minute"], current_schedule,
        IntradayTimeframe.FIVE_MINUTES,
    )

    phase = select_intraday_analysis_phase(
        current_completed_15m_count=len(groups["current_fifteen_minute"]),
        current_completed_1h_count=len(groups["current_one_hour"]),
    )
    if phase is None:
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_PHASE_UNAVAILABLE")
    if len(groups["previous_one_hour"]) < 2:
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_PRIOR_1H_UNAVAILABLE")

    selected: list[SelectedCompletedCandle] = []
    selected.extend(_selected(
        groups["previous_daily"], EvidenceSessionRole.PREVIOUS_SESSION_DAILY,
    ))
    selected.extend(_selected(
        groups["previous_one_hour"][-2:],
        EvidenceSessionRole.PRIOR_SESSION_1H_CONTEXT,
    ))
    if phase is IntradayAnalysisPhase.OPENING:
        opening = groups["current_fifteen_minute"][0]
        constituent = tuple(
            item for item in groups["current_five_minute"]
            if opening.candle_start <= item.candle_start
            and item.candle_end <= opening.candle_end
        )
        _require_opening_constituents(opening, constituent)
        selected.extend(_selected((opening,), EvidenceSessionRole.CURRENT_SESSION_15M))
        selected.extend(_selected(constituent, EvidenceSessionRole.CURRENT_SESSION_5M))
    else:
        if len(groups["current_fifteen_minute"]) < 2:
            raise CompletedEvidenceError("COMPLETED_EVIDENCE_15M_UNAVAILABLE")
        selected.extend(_selected(
            groups["current_fifteen_minute"][-2:],
            EvidenceSessionRole.CURRENT_SESSION_15M,
        ))
        selected.extend(_selected(
            groups["current_five_minute"][-2:],
            EvidenceSessionRole.CURRENT_SESSION_5M,
        ))
    if phase is IntradayAnalysisPhase.FIRST_CURRENT_SESSION_1H:
        selected.extend(_selected(
            groups["current_one_hour"][:1],
            EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY,
        ))
    elif phase is IntradayAnalysisPhase.CURRENT_SESSION_ESTABLISHED:
        selected.extend(_selected(
            groups["current_one_hour"][-2:],
            EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY,
        ))

    ordered = tuple(sorted(selected, key=_selected_key))
    values = {
        "canonical_subject_identity": canonical_subject_identity,
        "analysis_boundary": analysis_boundary,
        "phase": phase,
        "calendar_identity": current_schedule.source_identity,
        "calendar_version": current_schedule.source_version,
        "market_identity": current_schedule.exchange,
        "current_market_session_identity": current_schedule.session_id,
        "previous_market_session_identity": previous_schedule.session_id,
        "selected_candles": ordered,
        "source_operation_identities": tuple(sorted({
            item.candle.source_operation_identity for item in ordered
        })),
        "provenance": provenance,
        "selection_policy_identity": COMPLETED_EVIDENCE_SELECTION_POLICY,
        "selection_policy_version": COMPLETED_EVIDENCE_SELECTION_POLICY_VERSION,
        "schema_identity": COMPLETED_EVIDENCE_SELECTION_IDENTITY,
        "schema_version": COMPLETED_EVIDENCE_SELECTION_VERSION,
    }
    return PhaseAwareCompletedEvidenceSelection(
        selection_identity=_identity("INTRADAY-COMPLETED-EVIDENCE-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-COMPLETED-EVIDENCE-", values
        ),
        **values,
    )


def _require_phase_shape(value: PhaseAwareCompletedEvidenceSelection) -> None:
    roles = tuple(item.session_role for item in value.selected_candles)
    counts = {role: roles.count(role) for role in EvidenceSessionRole}
    if (
        counts[EvidenceSessionRole.PREVIOUS_SESSION_DAILY] != 1
        or counts[EvidenceSessionRole.PRIOR_SESSION_1H_CONTEXT] != 2
        or (
            value.phase is IntradayAnalysisPhase.OPENING
            and (
                counts[EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY] != 0
                or counts[EvidenceSessionRole.CURRENT_SESSION_15M] != 1
                or counts[EvidenceSessionRole.CURRENT_SESSION_5M] != 3
            )
        )
        or (
            value.phase is IntradayAnalysisPhase.STRUCTURE
            and (
                counts[EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY] != 0
                or counts[EvidenceSessionRole.CURRENT_SESSION_15M] != 2
            )
        )
        or (
            value.phase is IntradayAnalysisPhase.FIRST_CURRENT_SESSION_1H
            and (
                counts[EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY] != 1
                or counts[EvidenceSessionRole.CURRENT_SESSION_15M] != 2
            )
        )
        or (
            value.phase is IntradayAnalysisPhase.CURRENT_SESSION_ESTABLISHED
            and (
                counts[EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY] != 2
                or counts[EvidenceSessionRole.CURRENT_SESSION_15M] != 2
            )
        )
    ):
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_PHASE_SHAPE_INVALID")


def _require_schedule_pair(
    current: MarketDaySchedule,
    previous: MarketDaySchedule,
    boundary: datetime,
) -> None:
    if (
        type(current) is not MarketDaySchedule
        or type(previous) is not MarketDaySchedule
        or not _aware(boundary)
        or current.status is not TradingDayStatus.TRADING
        or previous.status is not TradingDayStatus.TRADING
        or current.exchange != previous.exchange
        or previous.trading_date >= current.trading_date
        or current.source_identity != previous.source_identity
        or current.source_version != previous.source_version
    ):
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_SCHEDULE_INVALID")


def _require_schedule_candles(
    candles: tuple[GovernedHistoricalCandlePayload, ...],
    schedule: MarketDaySchedule,
    timeframe: IntradayTimeframe,
    *,
    allow_daily: bool = False,
) -> None:
    if any(item.timeframe is not timeframe for item in candles):
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_TIMEFRAME_MISMATCH")
    if allow_daily:
        if any(
            item.market_session_identity != schedule.session_id
            or item.candle_start.date() != schedule.trading_date
            for item in candles
        ):
            raise CompletedEvidenceError("COMPLETED_EVIDENCE_SESSION_MISMATCH")
        return
    expected = {
        (item.start, item.end)
        for item in expected_candle_boundaries(schedule, timeframe)
    }
    if any(
        item.market_session_identity != schedule.session_id
        or (item.candle_start, item.candle_end) not in expected
        for item in candles
    ):
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_SESSION_MISMATCH")


def _require_opening_constituents(
    opening: GovernedHistoricalCandlePayload,
    candles: tuple[GovernedHistoricalCandlePayload, ...],
) -> None:
    if (
        len(candles) != 3
        or tuple(sorted(candles, key=lambda item: item.candle_start)) != candles
        or candles[0].candle_start != opening.candle_start
        or candles[-1].candle_end != opening.candle_end
        or any(previous.candle_end != current.candle_start for previous, current in zip(candles, candles[1:]))
        or any(item.candle_end - item.candle_start != IntradayTimeframe.FIVE_MINUTES.duration for item in candles)
    ):
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_OPENING_5M_INVALID")


def _require_canonical_order(
    values: tuple[GovernedHistoricalCandlePayload, ...],
) -> None:
    if (
        tuple(sorted(values, key=lambda item: item.candle_start)) != values
        or len({(item.timeframe, item.candle_start, item.candle_end) for item in values})
        != len(values)
    ):
        raise CompletedEvidenceError("COMPLETED_EVIDENCE_ORDER_OR_DUPLICATE_INVALID")


def _selected(
    values: Sequence[GovernedHistoricalCandlePayload],
    role: EvidenceSessionRole,
) -> tuple[SelectedCompletedCandle, ...]:
    return tuple(
        SelectedCompletedCandle(
            candle=item,
            source_timestamp=item.candle_start,
            completion_boundary=item.candle_end,
            original_market_session_identity=item.market_session_identity,
            session_role=role,
        )
        for item in values
    )


def _selected_key(value: SelectedCompletedCandle) -> tuple[str, str, datetime]:
    return value.session_role.value, value.candle.timeframe.value, value.candle.candle_start


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


__all__ = [
    "COMPLETED_EVIDENCE_SELECTION_IDENTITY",
    "COMPLETED_EVIDENCE_SELECTION_POLICY",
    "COMPLETED_EVIDENCE_SELECTION_POLICY_VERSION",
    "COMPLETED_EVIDENCE_SELECTION_VERSION",
    "CompletedEvidenceError",
    "EvidenceSessionRole",
    "IntradayAnalysisPhase",
    "PhaseAwareCompletedEvidenceSelection",
    "SelectedCompletedCandle",
    "build_completed_evidence_selection",
    "phase_aware_historical_window",
    "select_intraday_analysis_phase",
]
