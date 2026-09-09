"""WO-07B chart correspondence; no questions, indicators or trading decisions.

The observation receipt is independent evidence, never inferred from intake
metadata. Current Browser intake supplies no such observations. Missing proof
therefore remains UNVERIFIABLE. Raw source facts are kept separate from the
machine's immutable Review/chart/selection association.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json

from kronos.instrument.visual_identity import (
    VisualIdentityResolver, VisualIdentityResolutionError, VisualIdentitySourceContext,
)
from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import CandleBoundary, CandleCompletion
from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload
from kronos.intraday.validation import (
    FactObservability, ValidationState, compare_completed_panel_time,
)
from kronos.market.derived_timeframes import DerivedBarEvidence, DerivedBarStatus, DerivedTimeframe, derive_session_four_hour_bars
from kronos.market.schedule import MarketSchedule, MarketDaySchedule, MarketWindow, TradingDayStatus, MarketAvailability, ScheduleFreshness, ScheduleIntegrity

CONTRACT = "KRONOS-INTRADAY-CHART-INPUT-CORRESPONDENCE-V1"
VERSION = "1.0.0"
NSE_PANELS = tuple(("NATIVE", t) for t in ("1D", "1H", "15M", "5M"))
MCX_PANELS = tuple((r, t) for r in ("REFERENCE", "NATIVE") for t in ("1D", "4H", "15M", "5M"))
CORE_CONTENT = ("candles", "identity", "timeframe", "price_axis", "time_axis", "context_lead_in")
OPTIONAL_CONTENT = ("volume", "cpr", "sma", "vwap", "rsi", "factual_levels")
CONTENT = CORE_CONTENT + OPTIONAL_CONTENT


class ContentRequirement(StrEnum):
    CORE_REQUIRED = "CORE_REQUIRED"
    QUESTION_REQUIRED = "QUESTION_REQUIRED"
    OPTIONAL = "OPTIONAL"


@dataclass(frozen=True, slots=True)
class ObservedChartPanel:
    role: str
    timeframe: str
    observed_subject: str | None
    venue: str | None
    # Reference display name resolves commodity context; listed series is a
    # separate visual fact. No listed-to-continuous membership is asserted.
    observed_series: str | None
    currency: str | None
    unit: str | None
    trading_date: date | None
    session: str | None
    timezone: str | None
    candle_start: datetime | None
    candle_end: datetime | None
    completion: CandleCompletion | None
    captured_at: datetime | None
    latest_visible_end: datetime | None
    entire_panel_observed: bool | None
    opinion_overlays_present: bool | None
    content: tuple[tuple[str, FactObservability], ...]

    def __post_init__(self):
        if (self.role not in {"NATIVE", "REFERENCE"}
            or self.timeframe not in {"1D", "1H", "4H", "15M", "5M"}
            or any(x is not None and not _text(x) for x in (
                self.observed_subject, self.venue, self.observed_series, self.currency,
                self.unit, self.session, self.timezone))
            or self.trading_date is not None and type(self.trading_date) is not date
            or any(x is not None and not _aware(x) for x in (
                self.candle_start, self.candle_end, self.captured_at, self.latest_visible_end))
            or self.completion is not None and type(self.completion) is not CandleCompletion
            or any(x is not None and type(x) is not bool for x in (
                self.entire_panel_observed, self.opinion_overlays_present))
            or type(self.content) is not tuple
            or any(type(x) is not tuple or len(x) != 2 or x[0] not in CONTENT
                   or type(x[1]) is not FactObservability for x in self.content)
            or len({k for k, _ in self.content}) != len(self.content)):
            raise ValueError("CHART_INPUT_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class ChartInputObservation:
    chart_revision_identity: str
    chart_payload_sha256: str
    review_cycle_identity: str
    probables_run_identity: str
    probable_result_identity: str
    # Provenance of the independent observation; not a Sponsor intent checkbox.
    observation_source_identity: str
    observed_at: datetime
    panels: tuple[ObservedChartPanel, ...]
    schema_identity: str = CONTRACT
    schema_version: str = VERSION

    def __post_init__(self):
        if (any(not _text(x) for x in (
            self.chart_revision_identity, self.review_cycle_identity,
            self.probables_run_identity, self.probable_result_identity,
            self.observation_source_identity))
            or len(self.chart_payload_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.chart_payload_sha256)
            or not _aware(self.observed_at) or type(self.panels) is not tuple
            or any(type(p) is not ObservedChartPanel for p in self.panels)
            or len({(p.role, p.timeframe) for p in self.panels}) != len(self.panels)
            or self.schema_identity != CONTRACT or self.schema_version != VERSION):
            raise ValueError("CHART_INPUT_RECEIPT_INVALID")

    @property
    def identity(self):
        return "INTRADAY-CHART-INPUT-" + sha256(observation_bytes(self)).hexdigest()


@dataclass(frozen=True, slots=True)
class ExpectedChartPanel:
    role: str
    timeframe: str
    canonical_subject: str
    visual_target: str
    venue: str
    analysis_boundary: datetime
    relationship_boundary: datetime
    source: GovernedHistoricalCandlePayload | DerivedBarEvidence | None
    schedule: MarketSchedule | None
    currency: str | None = None
    unit: str | None = None
    supporting_visual_only: bool = False


@dataclass(frozen=True, slots=True)
class ChartPanelResult:
    role: str
    timeframe: str
    identity: ValidationState
    temporal: ValidationState
    core_content: ValidationState
    overall: ValidationState
    reasons: tuple[str, ...]
    content: tuple[tuple[str, ContentRequirement, FactObservability], ...]
    source_identity: str | None
    visual_relationship_identity: str | None
    authority: str = "INDEPENDENT_MACHINE_CORRESPONDENCE"
    independent_correspondence: str = "NOT_INDEPENDENTLY_ESTABLISHED"


def content_projection(panel, question_required=()):
    """Future Q-family mapping is caller-owned; this slice freezes none."""
    if any(k not in OPTIONAL_CONTENT for k in question_required):
        raise ValueError("CHART_INPUT_CONTENT_REQUIREMENT_INVALID")
    seen = dict(panel.content) if panel is not None else {}
    return tuple((k, ContentRequirement.CORE_REQUIRED if k in CORE_CONTENT else
                  ContentRequirement.QUESTION_REQUIRED if k in question_required else
                  ContentRequirement.OPTIONAL,
                  seen.get(k, FactObservability.UNVERIFIABLE)) for k in CONTENT)


def compare_chart_panel(expected, observed, *, resolver, received_at, observed_at):
    """Pure adapter to DOMAIN-001/008 and the existing panel time comparison.

    No source from another subject/Review may be substituted by callers. The
    application constructs expectations from its exact retained selection.
    """
    S = ValidationState
    reasons = []
    identity, temporal, core = S.UNVERIFIABLE, S.UNVERIFIABLE, S.UNVERIFIABLE
    relation = None
    content = content_projection(observed)
    if observed is not None:
        if (observed.role, observed.timeframe) != (expected.role, expected.timeframe):
            identity = S.NOT_VALIDATED
            reasons.append("PANEL_ROLE_OR_TIMEFRAME_MISMATCH")
        elif observed.observed_subject is None or observed.venue is None or resolver is None:
            reasons.append("VISUAL_IDENTITY_NOT_PROVEN")
        else:
            try:
                resolved = resolver.resolve(
                    observed_visible_subject_identity=observed.observed_subject,
                    source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
                    governed_observation_boundary=expected.relationship_boundary,
                )
                relation = resolved.relationship_identity
                identity = S.VALIDATED if (
                    resolved.canonical_subject_identity == expected.visual_target
                    and observed.venue == expected.venue
                    and (expected.currency is None or observed.currency == expected.currency)
                    and (expected.unit is None or observed.unit == expected.unit)
                ) else S.NOT_VALIDATED
                if identity is S.NOT_VALIDATED:
                    reasons.append("VISUAL_SUBJECT_VENUE_OR_UNIT_MISMATCH")
            except VisualIdentityResolutionError:
                reasons.append("VISUAL_RELATIONSHIP_UNAVAILABLE_OR_AMBIGUOUS")
        core = S.VALIDATED if all(
            state is FactObservability.EXACT for _, requirement, state in content
            if requirement is ContentRequirement.CORE_REQUIRED
        ) else S.UNVERIFIABLE
        if observed.opinion_overlays_present is True:
            core = S.NOT_VALIDATED
            reasons.append("OPINION_OVERLAY_EXCLUDED")
        elif observed.opinion_overlays_present is None:
            core = S.UNVERIFIABLE
            reasons.append("OPINION_OVERLAY_ABSENCE_NOT_PROVEN")
        if observed.entire_panel_observed is not True:
            core = S.UNVERIFIABLE if core is not S.NOT_VALIDATED else core
            reasons.append("FULL_PANEL_COVERAGE_NOT_PROVEN")
        if (observed.latest_visible_end is not None
            and observed.latest_visible_end > expected.analysis_boundary):
            temporal = S.NOT_VALIDATED
            reasons.append("VISIBLE_EVIDENCE_AFTER_ANALYSIS_BOUNDARY")
        elif observed.latest_visible_end is None or observed.entire_panel_observed is not True:
            reasons.append("NO_FUTURE_EVIDENCE_NOT_PROVEN")
        else:
            try:
                temporal, reason = _compare_source_time(expected, observed, received_at, observed_at)
            except ValueError:
                temporal, reason = S.UNVERIFIABLE, "SOURCE_INTEGRITY_NOT_PROVEN"
            reasons.append(reason)
            if (temporal is S.VALIDATED
                and observed.latest_visible_end != observed.candle_end):
                temporal = S.NOT_VALIDATED
                reasons.append("LATEST_VISIBLE_ENDPOINT_MISMATCH")
    else:
        reasons.append("PANEL_OBSERVATION_NOT_RETAINED")
    overall = (S.NOT_VALIDATED if S.NOT_VALIDATED in (identity, temporal, core) else
               S.VALIDATED if all(x is S.VALIDATED for x in (identity, temporal, core)) else
               S.UNVERIFIABLE)
    source = expected.source
    if expected.supporting_visual_only:
        if expected.role != "REFERENCE" or source is not None or expected.schedule is not None:
            raise ValueError("SUPPORTING_REFERENCE_SOURCE_FORBIDDEN")
        # Visible identity/core and known contradictions are still checked. No
        # absent independent source/session is converted into verified truth.
        if observed is not None and observed.completion is CandleCompletion.INCOMPLETE:
            temporal = S.NOT_VALIDATED
            reasons.append("REFERENCE_VISIBLE_FORMING_CANDLE")
        if observed is not None and (
            any(t is not None and t > expected.analysis_boundary for t in
                (observed.candle_start, observed.candle_end, observed.latest_visible_end))
            or observed.candle_start is not None and observed.candle_end is not None
                and observed.candle_start >= observed.candle_end
            or observed.candle_end is not None and observed.captured_at is not None
                and observed.candle_end > observed.captured_at
            or observed.captured_at is not None and observed.captured_at > received_at):
            temporal = S.NOT_VALIDATED
            reasons.append("REFERENCE_VISIBLE_TIME_CONTRADICTION")
        if temporal is S.NOT_VALIDATED:
            overall = S.NOT_VALIDATED
        elif overall is not S.NOT_VALIDATED:
            overall = S.UNVERIFIABLE
        reasons.append("NOT_INDEPENDENTLY_ESTABLISHED")
    source_identity = (source.candle_identity if type(source) is GovernedHistoricalCandlePayload else
        "MCX-DERIVED-SOURCE-" + sha256(json.dumps(asdict(source), sort_keys=True, default=str).encode()).hexdigest()
        if type(source) is DerivedBarEvidence else None)
    return ChartPanelResult(expected.role, expected.timeframe, identity, temporal, core,
        overall, tuple(reasons), content,
        source_identity, relation,
        "SUPPORTING_VISUAL_CONTEXT_ONLY" if expected.supporting_visual_only else "INDEPENDENT_MACHINE_CORRESPONDENCE",
        "VALIDATED" if not expected.supporting_visual_only and overall is S.VALIDATED else "NOT_INDEPENDENTLY_ESTABLISHED")


def _compare_source_time(expected, observed, received_at, observed_at):
    S = ValidationState
    source, schedule = expected.source, expected.schedule
    if source is None or schedule is None:
        return S.UNVERIFIABLE, "COMPLETED_SOURCE_OR_SESSION_NOT_RETAINED"
    if (schedule.market_availability is MarketAvailability.UNAVAILABLE
        or schedule.freshness_status is not ScheduleFreshness.CURRENT
        or schedule.integrity_status is not ScheduleIntegrity.VALID
        or schedule.source_boundary > expected.analysis_boundary):
        return S.UNVERIFIABLE, "SESSION_AUTHORITY_UNAVAILABLE"
    if type(source) is GovernedHistoricalCandlePayload:
        # Reconstruct to enforce the immutable source's own integrity contract.
        source.__post_init__()
        start, end, timeframe = source.candle_start, source.candle_end, source.timeframe.value
        subject, session = source.canonical_subject_identity, source.market_session_identity
        completed = source.completion_state == "COMPLETE"
        if (source.available_at > expected.analysis_boundary
            or source.observation_boundary > expected.analysis_boundary):
            return S.UNVERIFIABLE, "SOURCE_UNAVAILABLE_AT_ANALYSIS"
        if source.exchange != expected.venue:
            return S.NOT_VALIDATED, "SOURCE_EXCHANGE_MISMATCH"
        day = MarketDaySchedule(schedule.exchange, schedule.trading_date,
            schedule.session_identity, schedule.timezone, TradingDayStatus.TRADING,
            tuple(MarketWindow(w.window_open, w.window_close) for w in schedule.windows),
            schedule.source_identity, schedule.calendar_version)
        if CandleBoundary(schedule.trading_date, session, source.timeframe, start, end) not in expected_candle_boundaries(day, source.timeframe):
            return S.NOT_VALIDATED, "SOURCE_CANDLE_SESSION_MISMATCH"
    elif type(source) is DerivedBarEvidence:
        source.__post_init__()
        start, end, timeframe = source.derived_start, source.derived_end, source.derived_timeframe.value
        subject, session = source.canonical_instrument, source.session_identity
        completed = source.status is DerivedBarStatus.COMPLETE
        if (source.derived_timeframe is not DerivedTimeframe.FOUR_HOUR
            or source.calendar_identity != schedule.calendar_identity
            or source.calendar_version != schedule.calendar_version
            or source.source_market_data_boundary > expected.analysis_boundary
            or source.exchange_timezone != schedule.timezone):
            return S.UNVERIFIABLE, "DERIVED_SOURCE_CORRESPONDENCE_NOT_PROVEN"
        buckets = derive_session_four_hour_bars(canonical_instrument=subject, schedule=schedule,
            sixty_minute_candles=(), source_provider_identity=source.source_provider_identity,
            source_market_data_boundary=source.source_market_data_boundary,
            observed_at=expected.analysis_boundary)
        if not any((b.derived_start, b.derived_end, b.constituent_boundaries) ==
                   (start, end, source.constituent_boundaries) for b in buckets):
            return S.NOT_VALIDATED, "DERIVED_SOURCE_SESSION_MISMATCH"
    else:
        return S.UNVERIFIABLE, "SOURCE_TYPE_NOT_SUPPORTED"
    if (subject != expected.canonical_subject or session != schedule.session_identity
        or timeframe != expected.timeframe or schedule.exchange != expected.venue):
        return S.NOT_VALIDATED, "SOURCE_SUBJECT_SESSION_OR_TIMEFRAME_MISMATCH"
    if not completed or end > expected.analysis_boundary:
        return S.UNVERIFIABLE, "COMPLETED_CANDLE_NOT_PROVEN"
    return compare_completed_panel_time(
        expected=(schedule.trading_date, schedule.session_type, schedule.timezone, timeframe, start, end),
        observed=(observed.trading_date, observed.session, observed.timezone,
                  observed.timeframe, observed.candle_start, observed.candle_end),
        completion=observed.completion, captured_at=observed.captured_at,
        received_at=received_at, frozen_at=expected.analysis_boundary, observed_at=observed_at)


def observation_bytes(value):
    def encode(item):
        if isinstance(item, (datetime, date)):
            return item.isoformat()
        raise TypeError("CHART_INPUT_SERIALIZATION_INVALID")
    return json.dumps(asdict(value), sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), default=encode).encode() + b"\n"


def observation_from_bytes(payload):
    try:
        data = json.loads(payload)
        panels = []
        for item in data['panels']:
            for key in ('candle_start', 'candle_end', 'captured_at', 'latest_visible_end'):
                item[key] = datetime.fromisoformat(item[key]) if item[key] is not None else None
            item['trading_date'] = date.fromisoformat(item['trading_date']) if item['trading_date'] is not None else None
            item['completion'] = CandleCompletion(item['completion']) if item['completion'] is not None else None
            item['content'] = tuple((k, FactObservability(v)) for k, v in item['content'])
            panels.append(ObservedChartPanel(**item))
        data['panels'] = tuple(panels)
        data['observed_at'] = datetime.fromisoformat(data['observed_at'])
        result = ChartInputObservation(**data)
        if observation_bytes(result) != payload:
            raise ValueError("NONCANONICAL_CHART_INPUT")
        return result
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError("CHART_INPUT_RECEIPT_INVALID") from error


def _text(value):
    return type(value) is str and bool(value) and len(value) <= 256 and value == value.strip()


def _aware(value):
    return type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None
