from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.completed_evidence import (
    CompletedEvidenceError,
    PhaseAwareCompletedEvidenceSelection,
    PhaseAwareCompletedEvidenceSelectionV2,
    build_completed_evidence_selection,
    phase_aware_historical_window,
)
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    create_governed_historical_candle_payload,
)
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.intraday.probables_v2_persistence import (
    ProbablesV2Store,
    _artifact_bytes,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.schedule import (
    MarketDaySchedule,
    MarketSchedule,
    MarketWindow,
    TradingDayStatus,
)
from kronos.market.schedule_compatibility import (
    MARKET_SCHEDULE_COMPATIBILITY_IDENTITY,
    MARKET_SCHEDULE_COMPATIBILITY_VERSION,
    MarketScheduleCompatibilityError,
    MarketScheduleCompatibilityStatus,
    publish_mcx_schedule_compatibility,
    require_mcx_schedule_compatibility,
)


IST = ZoneInfo("Asia/Kolkata")
FAMILIES = (
    ("GOLDM", date(2026, 9, 4)),
    ("SILVERM", date(2026, 8, 31)),
    ("COPPER", date(2026, 8, 31)),
    ("NATGAS", date(2026, 8, 26)),
    ("NATURALGAS", date(2026, 8, 26)),
    ("CRUDE", date(2026, 9, 21)),
    ("CRUDEOIL", date(2026, 9, 21)),
)


def _pair(family: str, expiry: date):
    publisher = MarketCalendarPublisher()
    boundary = datetime.combine(expiry, datetime.min.time(), IST).replace(
        hour=9,
        minute=15,
    )
    profile = publisher.mcx_contract_session_profile(
        contract_family=family,
        contract_expiry=expiry,
        trading_date=expiry,
        observed_at=boundary,
    )
    assert profile.continuous_trading is not None
    current = _day(profile.continuous_trading)
    previous = CurrentMarketCalendarScheduleSource(
        publisher,
        observed_at=boundary,
        canonical_instrument_id=f"MCX-SUBJECT-{family}",
    ).previous_trading_schedule("MCX", expiry)
    artifact = publish_mcx_schedule_compatibility(
        calendar_publisher=publisher,
        contract_family=family,
        contract_expiry=expiry,
        current_schedule=current,
        previous_schedule=previous,
        analysis_boundary=boundary,
    )
    return publisher, boundary, current, previous, artifact


def _day(value: MarketSchedule) -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange=value.exchange,
        trading_date=value.trading_date,
        session_id=value.session_identity,
        timezone=value.timezone,
        status=TradingDayStatus.TRADING,
        windows=tuple(
            MarketWindow(item.window_open, item.window_close)
            for item in value.windows
        ),
        source_identity=value.source_identity,
        source_version=value.calendar_version,
        special_session="EXPIRY" in value.session_type,
    )


@pytest.mark.parametrize(("family", "expiry"), FAMILIES)
def test_all_five_families_publish_exact_directional_compatibility(
    family: str,
    expiry: date,
) -> None:
    _, boundary, current, previous, artifact = _pair(family, expiry)

    require_mcx_schedule_compatibility(
        artifact,
        current_schedule=current,
        previous_schedule=previous,
        analysis_boundary=boundary,
    )
    assert artifact.schema_identity == MARKET_SCHEDULE_COMPATIBILITY_IDENTITY
    assert artifact.schema_version == MARKET_SCHEDULE_COMPATIBILITY_VERSION
    assert artifact.base_schedule_identity == previous.source_identity
    assert artifact.derived_schedule_identity == current.source_identity
    assert artifact.current_session_identity != artifact.base_session_identity
    assert artifact.status is MarketScheduleCompatibilityStatus.CURRENT
    assert artifact.roll_continuity_authority is False
    assert artifact.analytical_authority is False
    assert artifact.trading_authority is False


def test_same_source_path_is_unchanged_and_rejects_unneeded_proof() -> None:
    publisher = MarketCalendarPublisher()
    boundary = datetime(2026, 9, 3, 9, 15, tzinfo=IST)
    adapter = CurrentMarketCalendarScheduleSource(
        publisher,
        observed_at=boundary,
    )
    current = adapter.schedule_for("MCX", boundary.date())
    previous = adapter.previous_trading_schedule("MCX", boundary.date())
    assert current is not None

    start, end = phase_aware_historical_window(
        current_schedule=current,
        previous_schedule=previous,
        observation_boundary=boundary,
    )
    assert start == previous.windows[0].opens_at
    assert end == boundary
    _, expiry_boundary, expiry_current, expiry_previous, artifact = _pair(
        "GOLDM", date(2026, 9, 4)
    )
    assert expiry_boundary > boundary
    with pytest.raises(CompletedEvidenceError, match="SCHEDULE_INVALID"):
        phase_aware_historical_window(
            current_schedule=current,
            previous_schedule=previous,
            observation_boundary=boundary,
            schedule_compatibility=artifact,
        )
    assert expiry_current.source_identity != expiry_previous.source_identity


def test_cross_source_without_exact_proof_and_clock_equality_fail_closed() -> None:
    _, boundary, current, previous, _ = _pair("GOLDM", date(2026, 9, 4))
    with pytest.raises(CompletedEvidenceError, match="SCHEDULE_INVALID"):
        phase_aware_historical_window(
            current_schedule=current,
            previous_schedule=previous,
            observation_boundary=boundary,
        )

    identical_clock_foreign = replace(
        previous,
        source_identity="FOREIGN-SCHEDULE",
        source_version="1",
    )
    with pytest.raises(CompletedEvidenceError, match="SCHEDULE_INVALID"):
        phase_aware_historical_window(
            current_schedule=replace(
                current,
                windows=tuple(
                    MarketWindow(
                        item.opens_at.replace(
                            year=boundary.year,
                            month=boundary.month,
                            day=boundary.day,
                        ),
                        item.closes_at.replace(
                            year=boundary.year,
                            month=boundary.month,
                            day=boundary.day,
                        ),
                    )
                    for item in previous.windows
                ),
            ),
            previous_schedule=identical_clock_foreign,
            observation_boundary=boundary,
        )


def test_wrong_stale_superseded_tampered_and_roll_bridge_proofs_fail_closed() -> None:
    _, boundary, current, previous, artifact = _pair("GOLDM", date(2026, 9, 4))
    _, _, _, _, wrong_family = _pair("CRUDE", date(2026, 9, 21))
    invalid_cases = (
        (wrong_family, boundary),
        (artifact, boundary + timedelta(seconds=1)),
    )
    for value, observed in invalid_cases:
        with pytest.raises(
            MarketScheduleCompatibilityError,
            match="NOT_APPLICABLE",
        ):
            require_mcx_schedule_compatibility(
                value,
                current_schedule=current,
                previous_schedule=previous,
                analysis_boundary=observed,
            )

    superseded = object.__new__(type(artifact))
    for name, value in artifact.__dict__.items() if hasattr(artifact, "__dict__") else ():
        object.__setattr__(superseded, name, value)
    # slots-based immutable records are cloned explicitly for hostile-input tests.
    for name in artifact.__slots__:
        if name in {"__weakref__", "status", "superseded_by_identity"}:
            continue
        object.__setattr__(superseded, name, getattr(artifact, name))
    object.__setattr__(superseded, "status", MarketScheduleCompatibilityStatus.SUPERSEDED)
    object.__setattr__(superseded, "superseded_by_identity", "NEW-PROOF")
    with pytest.raises(MarketScheduleCompatibilityError, match="NOT_APPLICABLE"):
        require_mcx_schedule_compatibility(
            superseded,
            current_schedule=current,
            previous_schedule=previous,
            analysis_boundary=boundary,
        )

    roll_bridge = object.__new__(type(artifact))
    for name in artifact.__slots__:
        if name in {"__weakref__", "roll_continuity_authority"}:
            continue
        object.__setattr__(roll_bridge, name, getattr(artifact, name))
    object.__setattr__(roll_bridge, "roll_continuity_authority", True)
    with pytest.raises(MarketScheduleCompatibilityError, match="NOT_APPLICABLE"):
        require_mcx_schedule_compatibility(
            roll_bridge,
            current_schedule=current,
            previous_schedule=previous,
            analysis_boundary=boundary,
        )

    with pytest.raises(MarketScheduleCompatibilityError, match="INVALID"):
        replace(artifact, integrity_identity="TAMPERED")


@pytest.mark.parametrize(
    "schedule_name,changes",
    (
        ("current", {"session_id": "FOREIGN-CURRENT-SESSION"}),
        ("previous", {"session_id": "FOREIGN-PREVIOUS-SESSION"}),
        ("previous", {"exchange": "NSE"}),
        ("previous", {"source_identity": "FOREIGN-MARKET-SCHEDULE"}),
        (
            "previous",
            {"status": TradingDayStatus.NON_TRADING, "windows": ()},
        ),
    ),
)
def test_wrong_session_exchange_lineage_and_invalid_schedule_fail_closed(
    schedule_name: str,
    changes: dict[str, object],
) -> None:
    _, boundary, current, previous, artifact = _pair(
        "GOLDM", date(2026, 9, 4)
    )
    schedules = {"current": current, "previous": previous}
    schedules[schedule_name] = replace(schedules[schedule_name], **changes)
    with pytest.raises(
        MarketScheduleCompatibilityError,
        match="NOT_APPLICABLE",
    ):
        require_mcx_schedule_compatibility(
            artifact,
            current_schedule=schedules["current"],
            previous_schedule=schedules["previous"],
            analysis_boundary=boundary,
        )


def test_wrong_trading_date_and_foreign_pair_fail_closed() -> None:
    _, boundary, current, previous, artifact = _pair(
        "GOLDM", date(2026, 9, 4)
    )
    _, _, _, foreign_previous, _ = _pair("CRUDE", date(2026, 9, 21))
    assert foreign_previous.trading_date != previous.trading_date
    for candidate in (foreign_previous, replace(previous, special_session=True)):
        with pytest.raises(
            MarketScheduleCompatibilityError,
            match="NOT_APPLICABLE",
        ):
            require_mcx_schedule_compatibility(
                artifact,
                current_schedule=current,
                previous_schedule=candidate,
                analysis_boundary=boundary,
            )


def test_invalid_schedule_lineage_and_wildcard_family_cannot_publish() -> None:
    publisher, boundary, current, previous, _ = _pair(
        "GOLDM", date(2026, 9, 4)
    )
    for invalid_previous in (
        replace(previous, source_identity="FOREIGN"),
        replace(previous, status=TradingDayStatus.NON_TRADING, windows=()),
    ):
        with pytest.raises(
            MarketScheduleCompatibilityError,
            match="SOURCE_MISMATCH",
        ):
            publish_mcx_schedule_compatibility(
                calendar_publisher=publisher,
                contract_family="GOLDM",
                contract_expiry=current.trading_date,
                current_schedule=current,
                previous_schedule=invalid_previous,
                analysis_boundary=boundary,
            )
    with pytest.raises(MarketScheduleCompatibilityError, match="SOURCE_UNAVAILABLE"):
        publish_mcx_schedule_compatibility(
            calendar_publisher=publisher,
            contract_family="*",
            contract_expiry=current.trading_date,
            current_schedule=current,
            previous_schedule=previous,
            analysis_boundary=boundary,
        )


def test_v2_selection_persists_both_lineages_and_replays_deterministically(
    tmp_path: Path,
) -> None:
    _, boundary, current, previous, artifact = _pair(
        "GOLDM", date(2026, 9, 4)
    )
    selection = _selection(
        current=current,
        previous=previous,
        boundary=boundary,
        compatibility=artifact,
    )
    assert type(selection) is PhaseAwareCompletedEvidenceSelectionV2
    assert selection.current_schedule_lineage.schedule == current
    assert selection.previous_schedule_lineage.schedule == previous
    assert selection.schedule_compatibility == artifact

    store = ProbablesV2Store(tmp_path.resolve())
    compatibility_path = store.retain_schedule_compatibility(artifact)
    selection_path = store.retain_selection(selection)
    assert "market-schedule-compatibility-v1" in compatibility_path.parts
    assert "completed-evidence-v2" in selection_path.parts
    assert store.load_schedule_compatibility(artifact.compatibility_identity) == artifact
    assert store.load_selection(selection.selection_identity) == selection
    assert store.retain_schedule_compatibility(artifact) == compatibility_path
    assert store.retain_selection(selection) == selection_path


def test_v1_selection_schema_and_serialized_shape_remain_unchanged() -> None:
    publisher = MarketCalendarPublisher()
    boundary = datetime(2026, 9, 3, 9, 15, tzinfo=IST)
    adapter = CurrentMarketCalendarScheduleSource(publisher, observed_at=boundary)
    current = adapter.schedule_for("MCX", boundary.date())
    previous = adapter.previous_trading_schedule("MCX", boundary.date())
    assert current is not None
    selection = _selection(
        current=current,
        previous=previous,
        boundary=boundary,
        compatibility=None,
    )
    assert type(selection) is PhaseAwareCompletedEvidenceSelection
    assert selection.schema_identity.endswith("SELECTION-V1")
    encoded = _artifact_bytes(selection)
    assert b"schedule_compatibility" not in encoded
    assert b"current_schedule_lineage" not in encoded


def _selection(
    *,
    current: MarketDaySchedule,
    previous: MarketDaySchedule,
    boundary: datetime,
    compatibility,
):
    subject = "MCX-SUBJECT-GOLDM"
    previous_daily = (
        _candle(
            subject,
            previous,
            IntradayTimeframe.DAILY,
            previous.windows[0].opens_at,
            previous.windows[-1].closes_at,
            boundary,
        ),
    )
    previous_hours = tuple(
        _candle(
            subject,
            previous,
            IntradayTimeframe.ONE_HOUR,
            item.start,
            item.end,
            boundary,
        )
        for item in (
            _last_two_hour_boundaries(previous)
        )
    )
    opening_start = current.windows[0].opens_at
    opening_end = opening_start + timedelta(minutes=15)
    opening = (
        _candle(
            subject,
            current,
            IntradayTimeframe.FIFTEEN_MINUTES,
            opening_start,
            opening_end,
            boundary,
        ),
    )
    five = tuple(
        _candle(
            subject,
            current,
            IntradayTimeframe.FIVE_MINUTES,
            opening_start + timedelta(minutes=5 * index),
            opening_start + timedelta(minutes=5 * (index + 1)),
            boundary,
        )
        for index in range(3)
    )
    return build_completed_evidence_selection(
        canonical_subject_identity=subject,
        analysis_boundary=boundary,
        current_schedule=current,
        previous_schedule=previous,
        previous_daily=previous_daily,
        previous_one_hour=previous_hours,
        current_one_hour=(),
        current_fifteen_minute=opening,
        current_five_minute=five,
        provenance=("ADR-0028",),
        schedule_compatibility=compatibility,
    )


def _last_two_hour_boundaries(schedule: MarketDaySchedule):
    from kronos.intraday.candles import expected_candle_boundaries

    return expected_candle_boundaries(
        schedule,
        IntradayTimeframe.ONE_HOUR,
    )[-2:]


def _candle(
    subject: str,
    schedule: MarketDaySchedule,
    timeframe: IntradayTimeframe,
    start: datetime,
    end: datetime,
    boundary: datetime,
) -> GovernedHistoricalCandlePayload:
    return create_governed_historical_candle_payload(
        canonical_subject_identity=subject,
        exchange="MCX",
        market_identity="MCX",
        market_session_identity=schedule.session_id,
        timeframe=timeframe,
        candle_start=start,
        candle_end=end,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=100,
        observation_boundary=boundary,
        provider_source_identity="DOMAIN-006:KITE:HISTORICAL",
        source_operation_identity="WO-A4-OFFLINE-TEST",
        provenance=("ADR-0028",),
    )
